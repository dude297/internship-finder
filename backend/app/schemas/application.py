from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.enums import ApplicationStatus
from app.schemas.common import BlankToNone


class ApplicationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApplicationStatus
    submitted_on: date | None = None
    notes: Annotated[Annotated[str, Field(max_length=10_000)] | None, BlankToNone] = None
    next_action: Annotated[Annotated[str, Field(max_length=200)] | None, BlankToNone] = None
    next_action_due: date | None = None
    interview_at: datetime | None = None


class ApplicationResponse(ApplicationBody):
    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    updated_at: datetime
