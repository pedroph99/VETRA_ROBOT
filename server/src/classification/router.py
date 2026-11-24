"""Foto binária via HTTP; sem rótulo verdadeiro nem cenário na requisição."""

import warnings
from io import BytesIO

from fastapi import APIRouter, HTTPException, Query, Request
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from server.src.classification.model import ModelBusy
from server.src.classification.schemas import Prediction

router = APIRouter(prefix="/api/classification", tags=["classificação"])
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000


def decode_image(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in ("JPEG", "PNG"):
                    raise ValueError("Use JPEG ou PNG.")
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError("Imagem excede 16 megapixels.")
                image.load()
                return image.convert("RGB")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise HTTPException(
            422, "Imagem inválida: envie JPEG/PNG com até 16 megapixels."
        ) from exc


@router.get("/health")
def health(request: Request):
    classifier = getattr(request.app.state, "classifier", None)
    return {
        "ready": classifier is not None,
        "mode": "YOLOv5s-cls" if classifier else "unavailable",
    }


@router.post(
    "/predict",
    response_model=Prediction,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
)
async def predict(request: Request, crop: str = Query(min_length=1, max_length=60)):
    classifier = getattr(request.app.state, "classifier", None)
    if classifier is None:
        raise HTTPException(
            503, "Modelo indisponível; não há fallback para resultado simulado."
        )
    if crop not in classifier.knowledge.data["culturas"]:
        raise HTTPException(422, "Cultura não suportada nesta integração.")
    if request.headers.get("content-type", "").split(";")[0].strip() not in (
        "image/jpeg",
        "image/png",
    ):
        raise HTTPException(
            415, "Envie o corpo binário com Content-Type image/jpeg ou image/png."
        )
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_BYTES:
            raise HTTPException(413, "Foto excede 5 MiB.")
        data.extend(chunk)
    image = await run_in_threadpool(decode_image, data)
    try:
        return await run_in_threadpool(classifier.analyze, image, crop)
    except ModelBusy as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": "1"}) from exc
    finally:
        image.close()
