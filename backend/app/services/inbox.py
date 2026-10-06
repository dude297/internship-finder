"""Action Inbox (ADR-020): what needs the owner's attention today, in bounded sections.

Read-only and derived on read. Every section is one set-based statement (plus profile and
source-health lookups), so the statement count never grows with the catalog. Hidden opportunities
(ADR-017) are excluded everywhere. Nothing here changes eligibility, fit, or any stored state.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Date, cast, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.enums import (
    ApplicationStatus,
    FactReviewState,
    IngestionRunStatus,
    OpportunitySourceType,
)
from app.models import (
    Application,
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirementCandidate,
    OpportunitySourceRecord,
)
from app.repositories import get_profile
from app.schemas.inbox import InboxItem, InboxResponse, InboxSection
from app.services.discovery import is_open
from app.services.source_health import derive_health
from app.services.sources import latest_finished_statuses, list_sources

SECTION_LIMIT = 10  # items per section; `total` still counts everything
HIGH_FIT_MIN = 70  # fit score (0-100) for "new high fit"
NEW_DAYS = 7
CLOSING_DAYS = 14
VERIFY_BY_DAYS = 14  # verify_by already passed, or within this many days
ACTION_DUE_DAYS = 3  # next_action_due overdue or within this many days
INTERVIEW_DAYS = 7
STALE_DAYS = 14  # saved/applying with no update this long
# Finished applications need no follow-up.
_DONE = (ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN)
_UNHEALTHY = ("warning", "stale", "failing")


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _section(db: Session, stmt: Any) -> list[Any]:
    """Rows of `stmt` limited to SECTION_LIMIT; the last column is the section's full count."""
    return list(db.execute(stmt.limit(SECTION_LIMIT)).all())


def _total() -> Any:
    return func.count().over().label("total")


def _new_high_fit(db: Session, today: date) -> InboxSection:
    profile = get_profile(db)
    if profile is None:
        return InboxSection(total=0, items=[])
    latest = (
        select(OpportunityEvaluation.opportunity_id, OpportunityEvaluation.fit_score)
        .where(OpportunityEvaluation.profile_id == profile.id)
        .ext(distinct_on(OpportunityEvaluation.opportunity_id))
        .order_by(
            OpportunityEvaluation.opportunity_id,
            OpportunityEvaluation.evaluated_at.desc(),
            OpportunityEvaluation.id.desc(),
        )
        .subquery()
    )
    rows = _section(
        db,
        select(Opportunity, latest.c.fit_score, _total())
        .join(latest, latest.c.opportunity_id == Opportunity.id)
        .where(
            Opportunity.dismissed_at.is_(None),
            is_open,
            Opportunity.first_seen_at >= _midnight(today - timedelta(days=NEW_DAYS)),
            latest.c.fit_score >= HIGH_FIT_MIN,
        )
        .order_by(
            latest.c.fit_score.desc(),
            Opportunity.posted_at.desc().nulls_last(),
            Opportunity.first_seen_at.desc(),
            Opportunity.id,
        ),
    )
    items = [
        InboxItem(
            id=o.id,
            title=o.title,
            organization=o.organization,
            reason=f"Fit {fit}, first found {o.first_seen_at.date()}",
            date=o.first_seen_at.date(),
        )
        for o, fit, _ in rows
    ]
    return InboxSection(total=rows[0][2] if rows else 0, items=items)


def _closing_soon(db: Session, today: date) -> InboxSection:
    rows = _section(
        db,
        select(Opportunity, _total())
        .where(
            Opportunity.dismissed_at.is_(None),
            is_open,
            Opportunity.application_deadline.between(today, today + timedelta(days=CLOSING_DAYS)),
        )
        .order_by(Opportunity.application_deadline, Opportunity.id),
    )
    items = [
        InboxItem(
            id=o.id,
            title=o.title,
            organization=o.organization,
            reason=f"Application deadline {o.application_deadline}",
            date=o.application_deadline,
        )
        for o, _ in rows
    ]
    return InboxSection(total=rows[0][1] if rows else 0, items=items)


def _pending_review(db: Session) -> InboxSection:
    pending = (
        select(
            OpportunityRequirementCandidate.opportunity_id.label("opportunity_id"),
            func.count().label("n"),
        )
        .where(OpportunityRequirementCandidate.review_state == FactReviewState.PENDING)
        .group_by(OpportunityRequirementCandidate.opportunity_id)
        .subquery()
    )
    rows = _section(
        db,
        select(Opportunity, pending.c.n, _total())
        .join(pending, pending.c.opportunity_id == Opportunity.id)
        .where(Opportunity.dismissed_at.is_(None), is_open)
        .order_by(pending.c.n.desc(), Opportunity.first_seen_at.desc(), Opportunity.id),
    )
    items = [
        InboxItem(
            id=o.id,
            title=o.title,
            organization=o.organization,
            reason=f"{n} suggested requirement{'s' if n != 1 else ''} to review",
        )
        for o, n, _ in rows
    ]
    return InboxSection(total=rows[0][2] if rows else 0, items=items)


def _source_warnings(db: Session, now: datetime) -> InboxSection:
    statuses = latest_finished_statuses(db)
    items: list[InboxItem] = []
    for source in list_sources(db):
        health = derive_health(
            enabled=source.enabled,
            latest_finished_status=statuses.get(source.id),
            last_success_at=source.last_success_at,
            consecutive_failures=0,  # health status doesn't read it
            now=now,
        )
        if health.health not in _UNHEALTHY:
            continue
        failed = statuses.get(source.id) is IngestionRunStatus.FAILED
        items.append(
            InboxItem(
                id=source.id,
                title=source.display_name,
                organization=source.kind.value,
                reason=f"Source {health.health}" + (" (last run failed)" if failed else ""),
                date=source.last_success_at.date() if source.last_success_at else None,
            )
        )
    return InboxSection(total=len(items), items=items[:SECTION_LIMIT])


def _program_verify_by(db: Session, today: date) -> InboxSection:
    registry = (
        select(OpportunitySourceRecord.id)
        .where(
            OpportunitySourceRecord.opportunity_id == Opportunity.id,
            OpportunitySourceRecord.source_type == OpportunitySourceType.CURATED_REGISTRY,
            OpportunitySourceRecord.is_active,
        )
        .exists()
    )
    rows = _section(
        db,
        select(Opportunity, _total())
        .where(
            Opportunity.dismissed_at.is_(None),
            registry,
            Opportunity.verify_by <= today + timedelta(days=VERIFY_BY_DAYS),
        )
        .order_by(Opportunity.verify_by, Opportunity.id),
    )
    items = [
        InboxItem(
            id=o.id,
            title=o.title,
            organization=o.organization,
            reason=(
                f"Dates need re-checking (verify by {o.verify_by})"
                if o.verify_by is not None and o.verify_by <= today
                else f"Verify dates by {o.verify_by}"
            ),
            date=o.verify_by,
        )
        for o, _ in rows
    ]
    return InboxSection(total=rows[0][1] if rows else 0, items=items)


def _applications(db: Session, today: date) -> InboxSection:
    interview_from = _midnight(today)
    interview_to = _midnight(today + timedelta(days=INTERVIEW_DAYS + 1))
    stale_before = _midnight(today - timedelta(days=STALE_DAYS))
    due = Application.next_action_due <= today + timedelta(days=ACTION_DUE_DAYS)
    interview = (Application.interview_at >= interview_from) & (
        Application.interview_at < interview_to
    )
    stale = Application.status.in_((ApplicationStatus.SAVED, ApplicationStatus.APPLYING)) & (
        Application.updated_at < stale_before
    )
    soonest = func.least(
        Application.next_action_due, cast(func.timezone("UTC", Application.interview_at), Date)
    )
    rows = _section(
        db,
        select(Application, Opportunity, _total())
        .join(Opportunity, Opportunity.id == Application.opportunity_id)
        .where(
            Opportunity.dismissed_at.is_(None),
            Application.status.not_in(_DONE),
            due | interview | stale,
        )
        .order_by(soonest.asc().nulls_last(), Application.updated_at, Application.id),
    )
    items: list[InboxItem] = []
    for a, o, _ in rows:
        # The most urgent applicable reason wins: due action, then interview, then stale.
        if a.next_action_due is not None and a.next_action_due <= today + timedelta(
            days=ACTION_DUE_DAYS
        ):
            what = a.next_action or "Follow up"
            reason, when = f"{what} (due {a.next_action_due})", a.next_action_due
        elif a.interview_at is not None and interview_from <= a.interview_at < interview_to:
            reason = f"Interview {a.interview_at:%Y-%m-%d %H:%M} UTC"
            when = a.interview_at.date()
        else:
            reason = f"No update since {a.updated_at.date()} ({a.status.value})"
            when = a.updated_at.date()
        items.append(
            InboxItem(id=o.id, title=o.title, organization=o.organization, reason=reason, date=when)
        )
    return InboxSection(total=rows[0][2] if rows else 0, items=items)


def build_inbox(
    db: Session, today: date | None = None, now: datetime | None = None
) -> InboxResponse:
    """The one place the inbox reads the clock (server UTC); tests pass `today`/`now`."""
    now = now or datetime.now(UTC)
    today = today or now.date()
    return InboxResponse(
        today=today,
        new_high_fit=_new_high_fit(db, today),
        closing_soon=_closing_soon(db, today),
        pending_requirement_review=_pending_review(db),
        source_warnings=_source_warnings(db, now),
        program_verify_by=_program_verify_by(db, today),
        applications=_applications(db, today),
    )
