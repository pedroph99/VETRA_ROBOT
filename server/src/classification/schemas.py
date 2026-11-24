"""Contrato da resposta pública; escore do modelo separado da interpretação."""

from typing import Literal

from pydantic import BaseModel, Field


class ClassScore(BaseModel):
    classe: str
    probabilidade_softmax: float = Field(ge=0, le=1)


class Interpretation(BaseModel):
    knowledge_version: str
    symptoms: list[str]
    possible_causes: list[dict]
    warnings: list[str]
    disease_hypothesis: str | None
    sources: list[str]
    next_step: str


class Prediction(BaseModel):
    status: Literal["NORMAL", "SUSPECT", "ALERT"]
    problem: str
    confidence: float = Field(ge=0, le=1)
    detection: str
    simulated: Literal[False]
    crop: str
    predicted_class: str
    top5: list[ClassScore]
    inconclusive: bool
    interpretation: Interpretation
    model: dict | None = None
