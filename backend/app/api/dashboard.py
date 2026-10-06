from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession
from app.schemas.dashboard import DashboardResponse
from app.services import dashboard as service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

TODAY_MIN, TODAY_MAX = date(2000, 1, 1), date(2999, 12, 31)


@router.get("")
def read_dashboard(
    db: DbSession,
    today: Annotated[date | None, Query()] = None,
    tz_offset_minutes: Annotated[int, Query(ge=-840, le=840)] = 0,
) -> DashboardResponse:
    """ADR-025: the home overview. `today` defaults to the server's UTC date and exists so the
    browser can pass its local date and tests can pin it."""
    if today is not None and not TODAY_MIN <= today <= TODAY_MAX:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "today must be between 2000 and 2999."
        )
    return service.build_dashboard(db, today, tz_offset_minutes=tz_offset_minutes)
