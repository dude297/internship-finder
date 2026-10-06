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


class ProviderNew(BaseModel):
    provider: str  # ingestion source kind of an active record
    count: int


class WeekNew(BaseModel):
    week_start: dt.date  # client-local first day of a 7-day window
    count: int


class DiscoveryHealth(BaseModel):
    open_opportunities: int
    direct_sources: int  # open opportunities with an active direct ATS record
    independent_percent: float | None
    description_percent: float | None
    feed_only: int
    latest_successful_sync_at: dt.datetime | None
    sync_reason: str  # ok | stale | never_synced | no_sources
    sources_needing_attention: int  # warning, stale, or failing
    # New supply from first_seen_at, hidden opportunities excluded (ADR-025 amendment).
    new_today: int  # open, first seen on the client's local today
    new_this_week: int  # open, first seen in the last 7 local days including today
    new_this_week_independent: int  # ... with an active non-feed automated record
    new_this_week_by_provider: list[ProviderNew]  # top 5; a multi-source opportunity counts in each
    weekly_new: list[WeekNew]  # 8 weeks oldest first, including opportunities since closed
    closing_soon: int  # same count as the Inbox's "closing soon" section


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
