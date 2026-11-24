"""Servidor de inferência independente: uvicorn server.src.inference_app:app."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from server.src.classification.model import Classifier
from server.src.classification.router import router


@asynccontextmanager
async def lifespan(app):
    classifier = Classifier()
    await run_in_threadpool(classifier.load)
    app.state.classifier = classifier
    yield
    app.state.classifier = None


app = FastAPI(title="VETRA · Inferência PlantVillage", lifespan=lifespan)
app.include_router(router)
