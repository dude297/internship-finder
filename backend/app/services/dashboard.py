"""Home dashboard (ADR-025): one composed, read-only overview.

Reuses the Action Inbox's section queries (ADR-020), source coverage (ADR-013/015), and the data
age check, so the numbers match the pages they link to. Every part is one set-based statement (or
a fixed handful), so the statement count never grows with the catalog. Hidden opportunities
(ADR-017) are excluded from actions, high-fit, and the timeline.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from statistics import median
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.api.data_age import freshness_status
from app.enums import (
    ApplicationEventType,
    ApplicationStatus,
    EligibilityStatus,
    FactReviewState,
)
from app.models import (
    Application,
    ApplicationEvent,
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirementCandidate,
)
from app.repositories import get_profile
from app.schemas.dashboard import (
    Actions,
    DashboardResponse,
    DiscoveryHealth,
    Funnel,
    HighFit,
    HighFitItem,
    RequirementHealth,
    TimelineItem,
)
from app.schemas.inbox import InboxItem
from app.services import inbox
from app.services.discovery import is_open
from app.services.source_discovery import _coverage_row  # pyright: ignore[reportPrivateUsage]

HIGH_FIT_LIMIT = 5
UPCOMING_LIMIT = 8
UPCOMING_DAYS = 14  # follow-ups, interviews, deadlines, and verify-by dates this far ahead
MIN_RATE_DENOMINATOR = 5  # a rate over fewer applications than this is noise: null
MIN_MEDIAN_SAMPLES = 3  # a median over fewer timed applications than this is noise: null

_S = ApplicationStatus
_E = ApplicationEventType
_DONE = (_S.ACCEPTED, _S.REJECTED, _S.WITHDRAWN)
_SEEN_INTERVIEW = (_S.INTERVIEW, _S.OFFER, _S.ACCEPTED)
_SEEN_APPLIED = (_S.APPLIED, *_SEEN_INTERVIEW)


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _percent(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


def _rate(part: int, whole: int) -> float | None:
    """A 0-1 ratio, or null when the denominator is too small to mean anything."""
    return round(part / whole, 3) if whole >= MIN_RATE_DENOMINATOR else None


def _pipeline(db: Session) -> dict[ApplicationStatus, int]:
    rows = db.execute(select(Application.status, func.count()).group_by(Application.status))
    counts = {status: n for status, n in rows.all()}
    return {s: counts.get(s, 0) for s in ApplicationStatus}


def _high_fit(db: Session, today: date) -> HighFit:
    profile = get_profile(db)
    if profile is None:
        return HighFit(total=0, items=[])
    latest = (
        select(
            OpportunityEvaluation.opportunity_id,
            OpportunityEvaluation.fit_score,
            OpportunityEvaluation.eligibility_status,
        )
        .where(OpportunityEvaluation.profile_id == profile.id)
        .ext(distinct_on(OpportunityEvaluation.opportunity_id))
        .order_by(
            OpportunityEvaluation.opportunity_id,
            OpportunityEvaluation.evaluated_at.desc(),
            OpportunityEvaluation.id.desc(),
        )
        .subquery()
    )
    eligible_first = (latest.c.eligibility_status != EligibilityStatus.ELIGIBLE.value).asc()
    tracked = select(Application.id).where(Application.opportunity_id == Opportunity.id).exists()
    rows = db.execute(
        select(Opportunity, latest.c.fit_score, latest.c.eligibility_status, func.count().over())
        .join(latest, latest.c.opportunity_id == Opportunity.id)
        .where(
            Opportunity.dismissed_at.is_(None),
            is_open,
            ~tracked,  # not already being worked on (any application row)
            Opportunity.first_seen_at >= _midnight(today - timedelta(days=inbox.NEW_DAYS)),
            latest.c.eligibility_status.in_(
                (EligibilityStatus.ELIGIBLE.value, EligibilityStatus.NEEDS_VERIFICATION.value)
            ),
            latest.c.fit_score >= inbox.HIGH_FIT_MIN,
        )
        .order_by(
            eligible_first,
            latest.c.fit_score.desc(),
            Opportunity.first_seen_at.desc(),
            Opportunity.id,
        )
        .limit(HIGH_FIT_LIMIT)
    ).all()
    items = [
        HighFitItem(
            id=o.id,
            title=o.title,
            organization=o.organization,
            eligibility_status=str(status),
            fit_score=fit,
            first_seen=o.first_seen_at.date(),
        )
        for o, fit, status, _ in rows
    ]
    return HighFit(total=rows[0][3] if rows else 0, items=items)


def _inbox_timeline(items: list[InboxItem], kind: str, today: date) -> list[TimelineItem]:
    return [
        TimelineItem(kind=kind, id=i.id, title=i.title, organization=i.organization, date=i.date)
        for i in items
        if i.date is not None and i.date >= today
    ]


def _application_timeline(db: Session, today: date) -> list[TimelineItem]:
    end = today + timedelta(days=UPCOMING_DAYS)
    rows = db.execute(
        select(Application, Opportunity)
        .join(Opportunity, Opportunity.id == Application.opportunity_id)
        .where(
            Opportunity.dismissed_at.is_(None),
            Application.status.not_in(_DONE),
            or_(
                Application.next_action_due.between(today, end),
                (Application.interview_at >= _midnight(today))
                & (Application.interview_at < _midnight(end + timedelta(days=1))),
            ),
        )
        .order_by(Application.next_action_due.nulls_last(), Application.id)
        .limit(UPCOMING_LIMIT * 2)
    ).all()
    items: list[TimelineItem] = []
    for a, o in rows:
        if a.next_action_due is not None and today <= a.next_action_due <= end:
            items.append(
                TimelineItem(
                    kind="follow_up",
                    id=o.id,
                    title=a.next_action or "Follow up",
                    organization=o.organization,
                    date=a.next_action_due,
                )
            )
        if a.interview_at is not None and _midnight(today) <= a.interview_at:
            items.append(
                TimelineItem(
                    kind="interview",
                    id=o.id,
                    title=o.title,
                    organization=o.organization,
                    date=a.interview_at.astimezone(UTC).date(),
                    at=a.interview_at,
                )
            )
    return items


def _requirements(db: Session) -> RequirementHealth:
    rows = db.execute(
        select(OpportunityRequirementCandidate.review_state, func.count()).group_by(
            OpportunityRequirementCandidate.review_state
        )
    )
    counts = {state: n for state, n in rows.all()}
    return RequirementHealth(
        awaiting_review=counts.get(FactReviewState.PENDING, 0),
        accepted=counts.get(FactReviewState.ACCEPTED, 0),
        rejected=counts.get(FactReviewState.REJECTED, 0),
    )


def _discovery(db: Session, now: datetime) -> DiscoveryHealth:
    counts = _coverage_row(db, [])
    fresh = freshness_status(db)
    return DiscoveryHealth(
        open_opportunities=counts.active,
        direct_sources=counts.ats_backed,
        independent_percent=_percent(counts.independent, counts.active),
        description_percent=_percent(counts.with_description, counts.active),
        feed_only=counts.feed_only,
        latest_successful_sync_at=fresh.last_successful_sync_at,
        sync_reason=fresh.reason,
        sources_needing_attention=inbox._source_warnings(db, now).total,  # pyright: ignore[reportPrivateUsage]
    )


def _funnel(db: Session) -> Funnel:
    """Reached-stage counts from the current status plus recorded history, so applications that
    moved on (or were rejected/withdrawn after an interview) still count where they got to.
    Legacy rows have no history and are judged by status and timestamps alone."""
    seen_applied = func.coalesce(func.bool_or(ApplicationEvent.to_status == _S.APPLIED), False)
    seen_interview = func.coalesce(
        func.bool_or(
            (ApplicationEvent.to_status == _S.INTERVIEW)
            | (ApplicationEvent.event_type == _E.INTERVIEW_SCHEDULED)
        ),
        False,
    )
    seen_offer = func.coalesce(
        func.bool_or(ApplicationEvent.event_type == _E.OFFER_RECEIVED), False
    )
    flags = (
        select(
            Application.id.label("id"),
            Application.status.label("status"),
            (
                Application.applied_at.is_not(None)
                | Application.status.in_(_SEEN_APPLIED)
                | seen_applied
            ).label("applied"),
            (
                Application.interview_at.is_not(None)
                | Application.status.in_(_SEEN_INTERVIEW)
                | seen_interview
            ).label("interviewed"),
            (Application.status.in_((_S.OFFER, _S.ACCEPTED)) | seen_offer).label("offered"),
        )
        .select_from(Application)
        .outerjoin(ApplicationEvent, ApplicationEvent.application_id == Application.id)
        .group_by(Application.id)
        .subquery()
    )
    applied, interviewed, offered, accepted, rejected_early, withdrawn_early = db.execute(
        select(
            func.count().filter(flags.c.applied),
            func.count().filter(flags.c.interviewed),
            func.count().filter(flags.c.offered),
            func.count().filter(flags.c.status == _S.ACCEPTED),
            func.count().filter(flags.c.status == _S.REJECTED, ~flags.c.interviewed),
            func.count().filter(flags.c.status == _S.WITHDRAWN, ~flags.c.interviewed),
        )
    ).one()

    # Median days from applied_at to the first recorded interview/rejection/offer event.
    def first(*conditions: Any) -> Any:
        return func.min(ApplicationEvent.occurred_at).filter(or_(*conditions))

    timed: Sequence[Any] = db.execute(
        select(
            Application.applied_at,
            first(
                ApplicationEvent.to_status == _S.INTERVIEW,
                ApplicationEvent.event_type == _E.INTERVIEW_SCHEDULED,
            ),
            first(ApplicationEvent.to_status == _S.REJECTED),
            first(ApplicationEvent.event_type == _E.OFFER_RECEIVED),
        )
        .join(ApplicationEvent, ApplicationEvent.application_id == Application.id)
        .where(Application.applied_at.is_not(None))
        .group_by(Application.id)
    ).all()

    def median_days(column: int) -> float | None:
        days = [
            (row[column] - row[0]).total_seconds() / 86400
            for row in timed
            if row[column] is not None and row[column] >= row[0]
        ]
        return round(median(days), 1) if len(days) >= MIN_MEDIAN_SAMPLES else None

    return Funnel(
        applied=applied,
        interviewed=interviewed,
        offered=offered,
        accepted=accepted,
        rejected_before_interview=rejected_early,
        withdrawn_before_interview=withdrawn_early,
        applied_to_interview_rate=_rate(interviewed, applied),
        interview_to_offer_rate=_rate(offered, interviewed),
        offer_to_accepted_rate=_rate(accepted, offered),
        median_days_to_interview=median_days(1),
        median_days_to_rejection=median_days(2),
        median_days_to_offer=median_days(3),
    )


def build_dashboard(
    db: Session, today: date | None = None, now: datetime | None = None
) -> DashboardResponse:
    """The one place the dashboard reads the clock (server UTC); tests pass `today`/`now`."""
    now = now or datetime.now(UTC)
    today = today or now.date()
    closing = inbox._closing_soon(db, today)  # pyright: ignore[reportPrivateUsage]
    pending = inbox._pending_review(db)  # pyright: ignore[reportPrivateUsage]
    apps = inbox._applications(  # pyright: ignore[reportPrivateUsage]
        db, today, stale_statuses=(_S.APPLYING, _S.APPLIED)
    )
    verify = inbox._program_verify_by(db, today)  # pyright: ignore[reportPrivateUsage]
    upcoming = [
        *_inbox_timeline(closing.items, "deadline", today),
        *_inbox_timeline(verify.items, "verify_by", today),
        *_application_timeline(db, today),
    ]
    upcoming.sort(
        key=lambda t: (t.at or _midnight(t.date), t.kind, str(t.id))  # chronological, stable
    )
    return DashboardResponse(
        today=today,
        actions=Actions(
            closing_soon=closing,
            pending_requirement_review=pending,
            applications=apps,
            total=closing.total + pending.total + apps.total,
        ),
        pipeline=_pipeline(db),
        high_fit_new=_high_fit(db, today),
        upcoming=upcoming[:UPCOMING_LIMIT],
        discovery=_discovery(db, now),
        requirements=_requirements(db),
        funnel=_funnel(db),
    )
