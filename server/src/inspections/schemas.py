"""Contratos e validações da API de inspeção."""
from typing import Annotated, Literal
from pydantic import BaseModel, Field

TimeOfDay = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Weekday = Annotated[int, Field(ge=0, le=6)]

class ScheduleUpdate(BaseModel):
    enabled: bool
    times: list[TimeOfDay] = Field(min_length=1, max_length=12)
    days: list[Weekday] = Field(min_length=1, max_length=7)

class ScenarioUpdate(BaseModel):
    scenario: Literal["normal", "aphids", "whitefly", "yellowing", "curling"]

class Command(BaseModel):
    command: Literal["START_MISSION", "STOP_MISSION", "PAUSE_MISSION", "RESUME_MISSION", "RETURN_HOME"]

class ObstacleUpdate(BaseModel):
    enabled: bool

class Acknowledgement(BaseModel):
    ok: bool = True
