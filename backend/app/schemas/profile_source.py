import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.enums import FactCategory, FactReviewState, ProfileSourceKind


class ProfileSourceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ProfileSourceKind
    original_filename: str | None
    content_type: str
    byte_size: int
    parser_name: str
    parser_version: str
    ingested_at: datetime
    pending_count: int
    accepted_count: int
    rejected_count: int


class ImportedFact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: FactCategory
    name: str
    description: str | None
    review_state: FactReviewState


class ProfileSourceDetail(ProfileSourceSummary):
    facts: list[ImportedFact]


# --- Review -------------------------------------------------------------------------------------


class AcceptItem(BaseModel):
    """Omitted `name`/`description` keeps the fact's current value (distinguished via
    `model_fields_set`, since `None` is a valid explicit value for `description`). Length limits
    differ by category (skill 100, course 150, others 150/2000); enforced in the service, not
    here, since the limit depends on which fact is being accepted."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str | None = None
    description: str | None = None


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accept: Annotated[list[AcceptItem], Field(max_length=200)] = Field(
        default_factory=list[AcceptItem]
    )
    reject: Annotated[list[uuid.UUID], Field(max_length=200)] = Field(
        default_factory=list[uuid.UUID]
    )


class ReviewResponse(BaseModel):
    source: ProfileSourceDetail
    catalog_pass: bool
    evaluated_opportunities: int
    unchanged_opportunities: int


class DeleteResponse(BaseModel):
    catalog_pass: bool
    evaluated_opportunities: int
    unchanged_opportunities: int
