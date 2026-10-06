import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession
from app.enums import ApplicationStatus
from app.models import Application
from app.schemas.application import ApplicationEventList, ApplicationPage
from app.services import applications as service

router = APIRouter(prefix="/applications", tags=["applications"])

TODAY_MIN, TODAY_MAX = date(2000, 1, 1), date(2999, 12, 31)


@router.get("")
def list_applications(
    db: DbSession,
    stage: Annotated[list[ApplicationStatus] | None, Query()] = None,
    company: Annotated[str | None, Query(max_length=200)] = None,
    due_soon: bool = False,
    follow_up_overdue: bool = False,
    interview_upcoming: bool = False,
    sort: service.Sort = "next_action",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    today: date | None = None,
    tz_offset_minutes: Annotated[int, Query(ge=-840, le=840)] = 0,
) -> ApplicationPage:
    """ADR-025: the owner's applications for the List and Pipeline views. `today` (the client's
    local date) drives due-soon and overdue; it defaults to the server's UTC date."""
    if today is not None and not TODAY_MIN <= today <= TODAY_MAX:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "today must be between 2000 and 2999."
        )
    return service.list_applications(
        db,
        today=today or datetime.now(UTC).date(),
        statuses=stage,
        company=company or None,
        due_soon=due_soon,
        follow_up_overdue=follow_up_overdue,
        interview_upcoming=interview_upcoming,
        sort=sort,
        limit=limit,
        offset=offset,
        tz_offset_minutes=tz_offset_minutes,
    )


@router.get("/{application_id}/events")
def read_events(application_id: uuid.UUID, db: DbSession) -> ApplicationEventList:
    """History from the feature's introduction onward, oldest first. Empty for older rows."""
    if db.get(Application, application_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found.")
    return ApplicationEventList.model_validate(
        {"items": service.list_events(db, application_id)}, from_attributes=True
    )
