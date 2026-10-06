from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession
from app.schemas.inbox import InboxResponse
from app.services import inbox as service

router = APIRouter(prefix="/inbox", tags=["inbox"])

TODAY_MIN, TODAY_MAX = date(2000, 1, 1), date(2999, 12, 31)


@router.get("")
def read_inbox(db: DbSession, today: Annotated[date | None, Query()] = None) -> InboxResponse:
    """ADR-020: the owner's action inbox. `today` defaults to the server's UTC date; it is
    bounded like the list's so date arithmetic can't overflow, and exists so tests can pin it."""
    if today is not None and not TODAY_MIN <= today <= TODAY_MAX:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "today must be between 2000 and 2999."
        )
    return service.build_inbox(db, today)
