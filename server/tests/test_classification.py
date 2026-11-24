import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from PIL import Image

from robot.state import State
from server.src.classification.knowledge import KnowledgeBase
from server.src.classification.model import ModelBusy
from server.src.main import make_app

TYLCV = "Tomato___Tomato_Yellow_Leaf_Curl_Virus"


def top(label=TYLCV, score=0.95):
    return [{"classe": label, "probabilidade_softmax": score}]


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.kb = KnowledgeBase()

    def test_vector_and_visual_differential_are_distinct(self):
        result = self.kb.interpret(top(), "Tomate")
        relations = {
            p["id"]: p["relacao"] for p in result["interpretation"]["possible_causes"]
        }
        self.assertEqual(
            relations, {"mosca_branca": "vetor", "pulgoes": "semelhanca_visual"}
        )
        self.assertFalse(result["simulated"])

    def test_mite_damage_is_not_insect_detection(self):
        result = self.kb.interpret(
            top("Tomato___Spider_mites Two-spotted_spider_mite"), "Tomate"
        )
        pest = result["interpretation"]["possible_causes"][0]
        self.assertEqual((pest["grupo"], pest["relacao"]), ("acaro", "dano_direto"))

    def test_healthy_has_no_pest_hypotheses(self):
        result = self.kb.interpret(top("Tomato___healthy"), "Tomate")
        self.assertEqual(result["status"], "NORMAL")
        self.assertEqual(result["interpretation"]["possible_causes"], [])

    def test_low_score_mismatch_and_unsupported_are_inconclusive(self):
        for label, score, crop in [
            (TYLCV, 0.5, "Tomate"),
            (TYLCV, 0.99, "Morango"),
            (TYLCV, 0.99, "Alface"),
        ]:
            result = self.kb.interpret(top(label, score), crop)
            self.assertEqual(result["status"], "SUSPECT")
            self.assertTrue(result["inconclusive"])
            self.assertEqual(result["interpretation"]["possible_causes"], [])
            self.assertIsNone(result["interpretation"]["disease_hypothesis"])

    def test_thrips_not_inferred_from_generic_leaf_spots(self):
        result = self.kb.interpret(top("Tomato___Septoria_leaf_spot"), "Tomate")
        self.assertEqual(result["interpretation"]["possible_causes"], [])
        thrips = next(p for p in self.kb.data["pragas"] if p["id"] == "tripes")
        self.assertFalse(thrips["classe_propria"])

    def test_citrus_vector_only_in_citrus(self):
        label = "Orange___Haunglongbing_(Citrus_greening)"
        self.assertEqual(
            self.kb.interpret(top(label), "Laranja")["interpretation"][
                "possible_causes"
            ][0]["id"],
            "psilideo_citros",
        )
        self.assertEqual(
            self.kb.interpret(top(label), "Tomate")["interpretation"][
                "possible_causes"
            ],
            [],
        )


class FakeClassifier:
    def __init__(self):
        self.knowledge = KnowledgeBase()
        self.calls = 0

    def analyze(self, image, crop):
        self.calls += 1
        self.size = image.size
        return self.knowledge.interpret(top(), crop)


class ClassificationApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = State(Path(self.temp.name), demo=True)
        self.classifier = FakeClassifier()
        self.app = make_app(self.state, self.classifier)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )
        buffer = io.BytesIO()
        Image.new("RGB", (32, 32)).save(buffer, "PNG")
        self.photo = buffer.getvalue()

    async def asyncTearDown(self):
        await self.client.aclose()
        self.state.store.close()
        self.temp.cleanup()

    async def post(self, data=None, crop="Tomate", content_type="image/png"):
        return await self.client.post(
            "/api/classification/predict",
            params={"crop": crop},
            content=self.photo if data is None else data,
            headers={"Content-Type": content_type},
        )

    async def test_real_image_contract(self):
        response = await self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["predicted_class"], TYLCV)
        self.assertEqual(self.classifier.size, (32, 32))
        self.assertNotIn("dataset_label", response.json())

    async def test_validation_prevents_model_calls(self):
        for data, crop, mime, code in [
            (b"invalid", "Tomate", "image/png", 422),
            (b"", "Tomate", "image/png", 422),
            (b"x", "Alface", "image/png", 422),
            (b"x", "Tomate", "text/plain", 415),
        ]:
            self.assertEqual((await self.post(data, crop, mime)).status_code, code)
        self.assertEqual(self.classifier.calls, 0)

    async def test_limit_and_unavailable(self):
        with patch("server.src.classification.router.MAX_BYTES", 10):
            self.assertEqual((await self.post()).status_code, 413)
        self.app.state.classifier = None
        self.assertEqual((await self.post()).status_code, 503)
        self.assertFalse(
            (await self.client.get("/api/classification/health")).json()["ready"]
        )

    async def test_busy_and_manual_scenario_conflict(self):
        with patch.object(self.classifier, "analyze", side_effect=ModelBusy("Ocupado")):
            self.assertEqual((await self.post()).status_code, 503)
        self.state.classification_mode = "model"
        response = await self.client.put(
            "/api/beds/1/scenario", json={"scenario": "whitefly"}
        )
        self.assertEqual(response.status_code, 409)

    async def test_pixel_limit(self):
        with patch("server.src.classification.router.MAX_PIXELS", 100):
            self.assertEqual((await self.post()).status_code, 422)
