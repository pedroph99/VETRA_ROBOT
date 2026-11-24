"""Carregamento único do checkpoint conhecido e inferência serializada em CPU."""

import hashlib
import threading
from pathlib import Path

from server.src.classification.knowledge import KnowledgeBase

SERVER = Path(__file__).resolve().parents[2]
WEIGHTS_SHA256 = "b310f6be35c8da88db598d5dbee771a9a420a98258b1d87679f7b9f277e14218"


class ModelBusy(Exception):
    pass


class Classifier:
    def __init__(self):
        self.lock = threading.Lock()
        self.knowledge = KnowledgeBase()
        self.model = None

    def load(self):
        with self.lock:
            if self.model is not None:
                return
            weights = SERVER / "models/best.pt"
            if hashlib.sha256(weights.read_bytes()).hexdigest() != WEIGHTS_SHA256:
                raise ValueError(
                    "Checkpoint diferente do arquivo validado; carregamento recusado."
                )
            import torch

            from server.src.classification.yolo import load_model

            torch.set_num_threads(4)
            self.model, self.transform = load_model(SERVER / "vendor/yolov5", weights)

    def analyze(self, image, crop):
        if not self.lock.acquire(blocking=False):
            raise ModelBusy("Modelo ocupado. Tente novamente.")
        try:
            if self.model is None:
                raise RuntimeError("Modelo não carregado")
            import numpy as np

            from server.src.classification.yolo import predict

            bgr = np.asarray(image.convert("RGB"))[:, :, ::-1].copy()
            result = self.knowledge.interpret(
                predict(self.model, self.transform, bgr), crop
            )
            result["model"] = dict(
                architecture="YOLOv5s-cls",
                weights_sha256=WEIGHTS_SHA256,
                classes=38,
                image_size=224,
                preprocessing="classify_transforms(224)",
            )
            return result
        finally:
            self.lock.release()
