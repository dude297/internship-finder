"""Application engine v2 (ADR-025): the owner's application tracking, its append-only history, and
the pipeline list.

Transitions are deliberately permissive (the owner may correct, reopen, or skip stages); history
is written in the caller's transaction on meaningful changes only. "Overdue" is derived on read.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.enums import ApplicationEventType as EventType
from app.enums import ApplicationStatus as Status
from app.models import Application, ApplicationEvent, Opportunity
from app.schemas.application import (
    ApplicationBody,
    ApplicationListItem,
    ApplicationPage,
)

ACTIVE = (Status.SAVED, Status.APPLYING, Status.APPLIED, Status.INTERVIEW, Status.OFFER)
DONE = (Status.ACCEPTED, Status.REJECTED, Status.WITHDRAWN)
DUE_SOON_DAYS = 3
Sort = Literal["next_action", "newest", "applied", "interview", "company", "stage"]
# Pipeline order, for the `stage` sort. Not a required sequence.
_STAGE_RANK = {s: i for i, s in enumerate((*ACTIVE, *DONE))}


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def save_application(
    db: Session, opportunity: Opportunity, body: ApplicationBody, now: datetime | None = None
) -> Application:
    """Create or update tracking and record what meaningfully changed, in the same transaction.

    Only fields the client sent are updated (an explicit null clears). `applied_at` is stamped
    when the status first becomes `applied` and it is still empty; a value the owner entered is
    never overwritten. Eligibility is untouched."""
    now = now or datetime.now(UTC)
    app = opportunity.application
    creating = app is None
    sent = body.model_dump() if creating else body.model_dump(exclude_unset=True)
    for key in ("interview_at", "applied_at"):
        if key in sent:
            sent[key] = _aware(sent[key])
    old: dict[str, Any] = {
        k: None if creating else getattr(app, k)
        for k in (
            "status",
            "notes",
            "next_action",
            "next_action_due",
            "interview_at",
            "applied_at",
        )
    }
    if app is None:
        app = opportunity.application = Application(**sent)
    else:
        for name, value in sent.items():
            setattr(app, name, value)
    if app.status is Status.APPLIED and old["status"] is not Status.APPLIED and not app.applied_at:
        app.applied_at = now
    db.flush()

    events: list[tuple[EventType, Status | None, Status | None, dict[str, Any]]] = []
    if creating:
        events.append((EventType.CREATED, None, app.status, {}))
    elif app.status is not old["status"]:
        events.append((EventType.STATUS_CHANGED, old["status"], app.status, {}))
    if app.status is Status.OFFER and old["status"] is not Status.OFFER:
        events.append((EventType.OFFER_RECEIVED, old["status"], app.status, {}))
    if app.next_action != old["next_action"]:
        events.append((EventType.NEXT_ACTION_CHANGED, None, None, {"next_action": app.next_action}))
    if app.next_action_due != old["next_action_due"]:
        meta = {"from": _iso(old["next_action_due"]), "to": _iso(app.next_action_due)}
        events.append((EventType.DEADLINE_CHANGED, None, None, meta))
    if app.interview_at != old["interview_at"]:
        kind = EventType.INTERVIEW_UPDATED if old["interview_at"] else EventType.INTERVIEW_SCHEDULED
        meta = {"from": _iso(old["interview_at"]), "to": _iso(app.interview_at)}
        events.append((kind, None, None, meta))
    # Notes are private: record that one was written, never its text.
    if app.notes and app.notes != old["notes"]:
        events.append((EventType.NOTE_ADDED, None, None, {"length": len(app.notes)}))
    for i, (kind, from_status, to_status, meta) in enumerate(events):
        db.add(
            ApplicationEvent(
                application_id=app.id,
                event_type=kind,
                # Microsecond offsets keep the order of events written together deterministic.
                occurred_at=now + timedelta(microseconds=i),
                from_status=from_status,
                to_status=to_status,
                metadata_json=meta,
            )
        )
    db.flush()
    return app


def list_events(db: Session, application_id: uuid.UUID) -> list[ApplicationEvent]:
    return list(
        db.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == application_id)
            .order_by(ApplicationEvent.occurred_at, ApplicationEvent.id)
        )
    )


def _order(stmt: Any, sort: Sort) -> Any:
    due = Application.next_action_due.asc().nulls_last()
    if sort == "newest":
        return stmt.order_by(Application.created_at.desc(), Application.id)
    if sort == "applied":
        return stmt.order_by(Application.applied_at.desc().nulls_last(), Application.id)
    if sort == "interview":
        return stmt.order_by(Application.interview_at.asc().nulls_last(), Application.id)
    if sort == "company":
        return stmt.order_by(
            func.lower(Opportunity.organization), Opportunity.title, Application.id
        )
    if sort == "stage":
        rank = case(_STAGE_RANK, value=Application.status, else_=len(_STAGE_RANK))
        return stmt.order_by(rank, due, Application.id)
    return stmt.order_by(due, Application.updated_at.desc(), Application.id)


def list_applications(
    db: Session,
    *,
    today: date,
    statuses: list[Status] | None = None,
    company: str | None = None,
    due_soon: bool = False,
    follow_up_overdue: bool = False,
    interview_upcoming: bool = False,
    sort: Sort = "next_action",
    limit: int = 100,
    offset: int = 0,
) -> ApplicationPage:
    active = Application.status.not_in(DONE)
    overdue = (Application.next_action_due < today) & active
    stmt = select(Application, Opportunity, overdue.label("overdue"), func.count().over()).join(
        Opportunity, Opportunity.id == Application.opportunity_id
    )
    if statuses:
        stmt = stmt.where(Application.status.in_(statuses))
    if company:
        term = company.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Opportunity.organization.ilike(f"%{term}%", escape="\\"))
    if due_soon:
        stmt = stmt.where(
            active,
            Application.next_action_due.between(today, today + timedelta(days=DUE_SOON_DAYS)),
        )
    if follow_up_overdue:
        stmt = stmt.where(overdue)
    if interview_upcoming:
        start = datetime.combine(today, time.min, tzinfo=UTC)
        stmt = stmt.where(active, Application.interview_at >= start)
    rows: list[Any] = list(db.execute(_order(stmt, sort).limit(limit).offset(offset)).all())
    items = [
        ApplicationListItem(
            id=a.id,
            opportunity_id=o.id,
            title=o.title,
            organization=o.organization,
            application_url=o.application_url,
            application_deadline=o.application_deadline,
            status=a.status,
            next_action=a.next_action,
            next_action_due=a.next_action_due,
            interview_at=a.interview_at,
            applied_at=a.applied_at,
            updated_at=a.updated_at,
            created_at=a.created_at,
            follow_up_overdue=bool(is_overdue),
        )
        for a, o, is_overdue, _ in rows
    ]
    total = rows[0][3] if rows else 0
    if not rows and offset:  # past the end: still report the real total
        total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    return ApplicationPage(today=today, total=total, items=items)
