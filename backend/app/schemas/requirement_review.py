"""Requirement candidate review API (ADR-012 §7). Contract shared by the backend and frontend."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.enums import (
    FactReviewState,
    RequirementAppliesAt,
    RequirementsAssessmentStatus,
    RequirementType,
)
from app.schemas.opportunity import RequirementResponse

MAX_REVIEW_ITEMS = 50


class RequirementCandidateResponse(BaseModel):
    """The original deterministic proposal. An edited accept changes only the linked canonical
    requirement, never these fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requirement_type: RequirementType
    value: dict[str, Any]
    applies_at: RequirementAppliesAt
    reference_date: date | None
    source_text: str
    extractor_name: str
    extractor_version: str
    review_state: FactReviewState
    # False: the current posting text no longer yields it (kept because it was reviewed).
    is_current: bool
    accepted_requirement_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class RequirementReviewResponse(BaseModel):
    opportunity_id: uuid.UUID
    requirements_assessment_status: RequirementsAssessmentStatus
    # Set when the source posting changed after review (ADR-012 §6); cleared by the next review.
    requirements_stale_since: datetime | None
    # Curated opportunities are never changed by sync (ADR-008 §8); suggestions still work.
    manually_curated: bool
    # Ordered: pending first, then accepted, then rejected; each by created_at, id.
    candidates: list[RequirementCandidateResponse]
    # The canonical requirements eligibility reads (from any extraction method).
    requirements: list[RequirementResponse]


class CandidateAccept(BaseModel):
    """Accept a candidate, optionally with an edited value/date. Omitted fields keep the
    candidate's. The requirement type can't change: reject and add it manually instead."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    value: dict[str, Any] | None = None
    applies_at: RequirementAppliesAt | None = None
    reference_date: date | None = None


class RequirementReviewRequest(BaseModel):
    """One atomic review batch. Every ID and edit is validated before anything changes; at most
    one evaluation of this opportunity follows. `assessment_status` is the owner's explicit
    assertion; without it, the first accepted requirement moves `unassessed` to `partial` and
    nothing ever becomes `complete` implicitly."""

    model_config = ConfigDict(extra="forbid")

    accept: list[CandidateAccept] = Field(
        default_factory=list[CandidateAccept], max_length=MAX_REVIEW_ITEMS
    )
    reject: list[uuid.UUID] = Field(default_factory=list[uuid.UUID], max_length=MAX_REVIEW_ITEMS)
    assessment_status: RequirementsAssessmentStatus | None = None


class RequirementReviewResult(BaseModel):
    review: RequirementReviewResponse
    # Whether a new evaluation row was appended (only when an eligibility input changed).
    evaluated: bool
