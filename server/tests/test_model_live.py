"""Teste opt-in: VETRA_TEST_MODEL=1, usa checkpoint real, socket HTTP e missão completa."""

import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

import httpx
import uvicorn

from robot.controller import Controller
from robot.demo_scene import DemoScene
from robot.inference_client import HttpDetector, PhotoBank
from robot.state import State
from server.src.classification.model import Classifier
from server.src.main import make_app


@unittest.skipUnless(
    os.environ.get("VETRA_TEST_MODEL") == "1",
    "Habilite VETRA_TEST_MODEL=1 para usar o checkpoint real",
)
class LiveModelTests(unittest.TestCase):
    def test_real_model_over_http_and_complete_mission(self):
        classifier = Classifier()
        classifier.load()
        identity = id(classifier.model)
        classifier.load()
        self.assertEqual(identity, id(classifier.model))
        names = set(
            classifier.model.names.values()
            if isinstance(classifier.model.names, dict)
            else classifier.model.names
        )
        self.assertTrue(set(classifier.knowledge.data["classes"]) <= names)
        with tempfile.TemporaryDirectory() as directory:
            state = State(Path(directory), demo=True)
            state.classification_mode = "model"
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            server = uvicorn.Server(
                uvicorn.Config(make_app(state, classifier), log_level="error")
            )
            thread = threading.Thread(
                target=server.run, kwargs={"sockets": [sock]}, daemon=True
            )
            thread.start()
            deadline = time.monotonic() + 15
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(server.started)
            base_url = f"http://127.0.0.1:{port}"
            controller = Controller(state, DemoScene(state), HttpDetector(base_url))
            try:
                with httpx.Client(base_url=base_url, timeout=30) as client:
                    bank = PhotoBank()
                    # Cada foto do banco atravessa a API real; rótulos apenas auditam a integração.
                    results = []
                    for row in bank.manifest["images"]:
                        image = bank.root / row["file"]
                        response = client.post(
                            "/api/classification/predict",
                            params={"crop": row["crop"]},
                            content=image.read_bytes(),
                            headers={"Content-Type": "image/jpeg"},
                        )
                        self.assertEqual(response.status_code, 200, response.text)
                        result = response.json()
                        self.assertFalse(result["simulated"])
                        self.assertEqual(len(result["top5"]), 5)
                        self.assertIn(result["predicted_class"], names)
                        results.append(result["predicted_class"] == row["label"])
                    print(
                        f"HTTP real: {sum(results)}/{len(results)} rótulos coincidentes (banco de simulação, não avaliação independente).",
                        flush=True,
                    )
                    controller.command("START_MISSION")
                    deadline = time.monotonic() + 90
                    while (
                        state.status not in ("FINISHED", "ERROR")
                        and time.monotonic() < deadline
                    ):
                        with state.lock:
                            controller.tick(0.2)
                        if controller.pending:
                            # Painel e controle continuam respondendo durante a inferência.
                            self.assertEqual(client.get("/api/status").status_code, 200)
                            time.sleep(0.01)
                    self.assertEqual(state.status, "FINISHED", state.error)
                    records = state.store.read("inspection", 20)
                    self.assertEqual(len(records), 12)
                    complete = [
                        r for r in records if r["analysis_state"] == "completed"
                    ]
                    unsupported = [
                        r for r in records if r["analysis_state"] == "unsupported_crop"
                    ]
                    self.assertEqual((len(complete), len(unsupported)), (7, 5))
                    for record in complete:
                        self.assertEqual(record["image_source"], "plantvillage")
                        self.assertEqual(record["image"], record["camera_image"])
                        self.assertEqual(client.get(record["image"]).status_code, 200)
                        self.assertEqual(
                            client.get(record["camera_image"]).status_code, 200
                        )
                        self.assertIn("interpretation", record)
                    print(
                        "Missão completa: 12 registros; 7 inferências HTTP e 5 canteiros de alface sem diagnóstico.",
                        flush=True,
                    )
            finally:
                controller.close()
                server.should_exit = True
                thread.join(10)
                sock.close()
                state.store.close()
