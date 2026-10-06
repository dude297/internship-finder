"""Home dashboard response (ADR-025). Contract shared by the backend and frontend."""

import datetime as dt
import uuid

from pydantic import BaseModel

from app.enums import ApplicationStatus
from app.schemas.inbox import InboxSection


class Actions(BaseModel):
    """Reuses the Action Inbox's sections (ADR-020), so the two never disagree."""

    closing_soon: InboxSection
    pending_requirement_review: InboxSection
    # follow-ups due/overdue, interviews within the window, stale applying/applied; see `kind`.
    applications: InboxSection
    total: int


class HighFitItem(BaseModel):
    id: uuid.UUID
    title: str
    organization: str
    eligibility_status: str
    fit_score: int
    first_seen: dt.date


class HighFit(BaseModel):
    total: int
    items: list[HighFitItem]


class TimelineItem(BaseModel):
    # deadline | follow_up | interview | verify_by
    kind: str
    id: uuid.UUID  # opportunity id
    title: str
    organization: str
    date: dt.date
    # Interviews only: the instant, rendered by the browser in its own time zone.
    at: dt.datetime | None = None


class DiscoveryHealth(BaseModel):
    open_opportunities: int
    direct_sources: int  # open opportunities with an active direct ATS record
    independent_percent: float | None
    description_percent: float | None
    feed_only: int
    latest_successful_sync_at: dt.datetime | None
    sync_reason: str  # ok | stale | never_synced | no_sources
    sources_needing_attention: int  # warning, stale, or failing


class RequirementHealth(BaseModel):
    """Counts of suggestions the extractor made, by the owner's review decision."""

    awaiting_review: int
    accepted: int
    rejected: int


class Funnel(BaseModel):
    applied: int
    interviewed: int
    offered: int
    accepted: int
    rejected_before_interview: int
    withdrawn_before_interview: int
    # Rates are null unless the denominator is at least MIN_RATE_DENOMINATOR.
    applied_to_interview_rate: float | None
    interview_to_offer_rate: float | None
    offer_to_accepted_rate: float | None
    # Median days from applied_at; null unless enough applications have both timestamps.
    median_days_to_interview: float | None
    median_days_to_rejection: float | None
    median_days_to_offer: float | None


class DashboardResponse(BaseModel):
    today: dt.date
    actions: Actions
    pipeline: dict[ApplicationStatus, int]
    high_fit_new: HighFit
    upcoming: list[TimelineItem]
    discovery: DiscoveryHealth
    requirements: RequirementHealth
    funnel: Funnel
