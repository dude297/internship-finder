import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import ApplicationEventType, ApplicationStatus
from app.schemas.common import BlankToNone


class ApplicationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApplicationStatus
    submitted_on: date | None = None
    notes: Annotated[Annotated[str, Field(max_length=10_000)] | None, BlankToNone] = None
    next_action: Annotated[Annotated[str, Field(max_length=200)] | None, BlankToNone] = None
    next_action_due: date | None = None
    interview_at: datetime | None = None
    # ADR-025: set automatically the first time status becomes `applied`; the owner may correct
    # it, and a manual value is never overwritten.
    applied_at: datetime | None = None

    @field_validator("applied_at")
    @classmethod
    def _plausible(cls, value: datetime | None) -> datetime | None:
        if value is not None and not datetime(2000, 1, 1, tzinfo=UTC) <= (
            value if value.tzinfo else value.replace(tzinfo=UTC)
        ) <= datetime(2999, 12, 31, tzinfo=UTC):
            raise ValueError("applied_at must be between 2000 and 2999.")
        return value


class ApplicationResponse(ApplicationBody):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    opportunity_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ApplicationEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: ApplicationEventType
    occurred_at: datetime
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus | None
    metadata_json: dict[str, Any]


class ApplicationEventList(BaseModel):
    items: list[ApplicationEventResponse]


class ApplicationListItem(BaseModel):
    """One row of the pipeline/list: the application, its opportunity's essentials, and the
    derived (never stored) overdue flag."""

    id: uuid.UUID
    opportunity_id: uuid.UUID
    title: str
    organization: str
    application_url: str | None
    application_deadline: date | None
    status: ApplicationStatus
    next_action: str | None
    next_action_due: date | None
    interview_at: datetime | None
    applied_at: datetime | None
    updated_at: datetime
    created_at: datetime
    follow_up_overdue: bool


class ApplicationPage(BaseModel):
    today: date
    total: int
    items: list[ApplicationListItem]
