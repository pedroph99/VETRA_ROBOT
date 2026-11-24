"""Estado injetado por aplicação, sem singleton global."""
from fastapi import Request

async def get_state(request: Request):
    return request.app.state.robot_state
