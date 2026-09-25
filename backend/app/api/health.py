from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/health")
def get_health() -> HealthResponse:
    """Liveness only: confirms the API process is up. Deliberately touches no database."""
    return HealthResponse(status="ok")
