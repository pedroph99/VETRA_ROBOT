"""Rotas HTTP; regras de negócio ficam em service.py."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from server.src.inspections import service
from server.src.inspections.dependencies import get_state
from server.src.inspections.schemas import Acknowledgement, Command, ObstacleUpdate, ScenarioUpdate, ScheduleUpdate

router = APIRouter(prefix="/api", tags=["inspeções"])
StateDependency = Annotated[object, Depends(get_state)]

@router.get("/status")
def status(state: StateDependency):
    return state.snapshot()

@router.post("/control", response_model=Acknowledgement)
def control(data: Command, state: StateDependency):
    try:
        service.command(state, data.command)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True}

@router.put("/settings", response_model=Acknowledgement)
def settings(data: ScheduleUpdate, state: StateDependency):
    service.update_schedule(state, data)
    return {"ok": True}

@router.put("/beds/{bed_id}/scenario", response_model=Acknowledgement)
def scenario(bed_id: int, data: ScenarioUpdate, state: StateDependency):
    try:
        service.update_scenario(state, bed_id, data.scenario)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True}

@router.put("/obstacle", response_model=Acknowledgement)
def obstacle(data: ObstacleUpdate, state: StateDependency):
    service.update_obstacle(state, data.enabled)
    return {"ok": True}

@router.get("/inspections")
def inspections(state: StateDependency, bed_id: int | None = None, status: str | None = None,
                limit: Annotated[int, Query(ge=1, le=500)] = 100,
                offset: Annotated[int, Query(ge=0)] = 0):
    return service.list_inspections(state, bed_id, status, limit, offset)

@router.get("/export")
def export(state: StateDependency):
    return Response(service.export_csv(state), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=inspecoes-estufa.csv"})
