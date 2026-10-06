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
from app.schemas.opportunity import FreshnessState, RequirementResponse

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


# --- Global review queue (ADR-024) -------------------------------------------------------------

MAX_QUEUE_PAGE = 100
MAX_BATCH_REJECT = 100


class QueueOpportunity(BaseModel):
    id: uuid.UUID
    title: str
    organization: str
    application_url: str | None
    first_seen_at: datetime
    requirements_assessment_status: RequirementsAssessmentStatus
    # Set when the posting changed after its last review (ADR-012 §6).
    requirements_stale_since: datetime | None
    # ADR-015: derived listing freshness, never a guarantee the posting is open.
    freshness: FreshnessState
    freshness_checked_at: datetime | None
    source_names: list[str]
    source_kinds: list[str]


class QueueItem(BaseModel):
    candidate: RequirementCandidateResponse
    opportunity: QueueOpportunity
    # The opportunity's canonical requirements (what eligibility reads).
    existing_requirements: list[RequirementResponse]
    # A canonical requirement that already means exactly this (same semantic key). Accepting
    # links to it instead of creating a second one (ADR-012 §7); the UI warns.
    duplicate_of: uuid.UUID | None


class QueueCategoryCount(BaseModel):
    requirement_type: RequirementType
    count: int


class QueueSummary(BaseModel):
    # Pending suggestions on visible (not hidden, not closed) opportunities, ignoring filters.
    pending_total: int
    by_type: list[QueueCategoryCount]
    # Reviewed candidates whose row last changed on `today` (UTC); see ADR-024 for the caveat.
    accepted_today: int
    rejected_today: int
    today: date
    extractor_versions: list[str]


class QueuePage(BaseModel):
    items: list[QueueItem]
    total: int  # matching the filters
    limit: int
    offset: int
    summary: QueueSummary


class BatchRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BATCH_REJECT)


class BatchRejectResult(BaseModel):
    rejected: int
    opportunities: int
    evaluated: int  # opportunities that received a new evaluation
