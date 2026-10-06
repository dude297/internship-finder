"""Action Inbox (ADR-020) and application follow-up fields. Synthetic data only.

`today` is pinned (2041-03-10) so every date window is deterministic."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from app.enums import (
    FactReviewState,
    IngestionRunStatus,
    IngestionSourceKind,
    OpportunitySourceType,
    RequirementAppliesAt,
    RequirementType,
)
from app.models import (
    Application,
    IngestionRun,
    IngestionSource,
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirementCandidate,
    OpportunitySourceRecord,
)
from app.services import inbox as inbox_service
from tests.test_api_workflow import create, put_profile

pytestmark = pytest.mark.postgres

TODAY = date(2041, 3, 10)


def at(day: date, hour: int = 12) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def days(n: int) -> date:
    return TODAY + timedelta(days=n)


def inbox(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/inbox", params={"today": TODAY.isoformat()})
    assert response.status_code == 200, response.text
    return response.json()


def titles(section: dict[str, Any]) -> list[str]:
    return [item["title"] for item in section["items"]]


def make(client: TestClient, title: str, **changes: Any) -> str:
    return create(client, title=title, application_deadline=None, **changes)["id"]


def set_fields(db: Session, opportunity_id: str, **values: Any) -> None:
    db.execute(update(Opportunity).where(Opportunity.id == opportunity_id).values(**values))
    db.commit()


def hide(client: TestClient, opportunity_id: str) -> None:
    assert client.put(f"/api/opportunities/{opportunity_id}/dismissal").status_code == 200


def registry_source(db: Session) -> IngestionSource:
    source = IngestionSource(
        kind=IngestionSourceKind.GREENHOUSE, identifier="inbox-test", display_name="Inbox Test"
    )
    db.add(source)
    db.flush()
    return source


def add_record(
    db: Session,
    opportunity_id: str,
    source: IngestionSource,
    source_type: OpportunitySourceType,
    active: bool = True,
) -> None:
    now = datetime.now(UTC)
    db.add(
        OpportunitySourceRecord(
            opportunity_id=uuid.UUID(opportunity_id),
            source_name=f"inbox-{uuid.uuid4()}",
            source_type=source_type,
            fetched_at=now,
            ingestion_source_id=source.id,
            is_active=active,
            closed_at=None if active else now,
        )
    )
    db.commit()


# --- New high fit ------------------------------------------------------------------------------


def test_new_high_fit_threshold_window_hidden_and_order(client: TestClient, db: Session) -> None:
    put_profile(client)
    first_seen = at(days(-2))
    rows = {
        "High 90": (90, first_seen, None),
        "Edge 70": (70, first_seen, None),
        "Low 69": (69, first_seen, None),
        "Old 99": (99, at(days(-8), 23), None),  # first found 8 days ago: outside the window
        "Window start 95": (95, datetime(2041, 3, 3, tzinfo=UTC), None),  # exactly 7 days
        "Tie newer": (80, first_seen, at(days(-1))),
        "Tie older": (80, first_seen, at(days(-5))),
        "Hidden 99": (99, first_seen, None),
    }
    ids: dict[str, str] = {}
    for title, (score, seen, posted) in rows.items():
        ids[title] = make(client, title)
        set_fields(db, ids[title], first_seen_at=seen, last_seen_at=seen, posted_at=posted)
        db.execute(
            update(OpportunityEvaluation)
            .where(OpportunityEvaluation.opportunity_id == ids[title])
            .values(fit_score=score)
        )
    db.commit()
    hide(client, ids["Hidden 99"])

    section = inbox(client)["new_high_fit"]
    assert titles(section) == [
        "Window start 95",
        "High 90",
        "Tie newer",
        "Tie older",
        "Edge 70",
    ]
    assert section["total"] == 5


def test_new_high_fit_needs_a_profile_and_open_posting(client: TestClient, db: Session) -> None:
    assert inbox(client)["new_high_fit"] == {"total": 0, "items": []}
    put_profile(client)
    closed = make(client, "Closed posting")
    set_fields(db, closed, first_seen_at=at(days(-1)), last_seen_at=at(days(-1)))
    db.execute(update(OpportunityEvaluation).values(fit_score=95))
    add_record(db, closed, registry_source(db), OpportunitySourceType.ATS, active=False)
    assert inbox(client)["new_high_fit"]["total"] == 0


# --- Closing soon ------------------------------------------------------------------------------


def test_closing_soon_window_hidden_and_closed(client: TestClient, db: Session) -> None:
    ids: dict[str, str] = {}
    for title, deadline in {
        "Today": days(0),
        "In 14": days(14),
        "In 15": days(15),
        "Yesterday": days(-1),
        "Hidden": days(2),
        "Closed": days(3),
        "In 5": days(5),
    }.items():
        ids[title] = create(client, title=title, application_deadline=deadline.isoformat())["id"]
    hide(client, ids["Hidden"])
    add_record(db, ids["Closed"], registry_source(db), OpportunitySourceType.ATS, active=False)

    section = inbox(client)["closing_soon"]
    assert titles(section) == ["Today", "In 5", "In 14"]
    assert section["total"] == 3
    assert section["items"][0]["date"] == TODAY.isoformat()


# --- Pending requirement review ----------------------------------------------------------------


def candidate(
    opportunity_id: str, state: FactReviewState, n: int
) -> OpportunityRequirementCandidate:
    return OpportunityRequirementCandidate(
        opportunity_id=uuid.UUID(opportunity_id),
        semantic_key=f"{n:064d}",
        requirement_type=RequirementType.MINIMUM_AGE,
        value={"years": 16 + n},
        applies_at=RequirementAppliesAt.PROGRAM_START,
        source_text="Must be 16.",
        extractor_name="test",
        extractor_version="1",
        review_state=state,
    )


def test_pending_requirement_review_counts_only_pending_visible(
    client: TestClient, db: Session
) -> None:
    two, one, accepted, hidden = (make(client, t) for t in ("Two", "One", "Accepted", "Hidden"))
    db.add_all(
        [
            candidate(two, FactReviewState.PENDING, 1),
            candidate(two, FactReviewState.PENDING, 2),
            candidate(one, FactReviewState.PENDING, 1),
            candidate(accepted, FactReviewState.REJECTED, 1),
            candidate(hidden, FactReviewState.PENDING, 1),
        ]
    )
    db.commit()
    hide(client, hidden)

    section = inbox(client)["pending_requirement_review"]
    assert titles(section) == ["Two", "One"]
    assert section["total"] == 2
    assert section["items"][0]["reason"].startswith("2 suggested requirements")


# --- Source warnings ---------------------------------------------------------------------------


def test_source_warnings_list_only_unhealthy_enabled_sources(
    client: TestClient, db: Session
) -> None:
    now = datetime.now(UTC)
    specs = {
        "healthy": (IngestionRunStatus.SUCCESS, now - timedelta(hours=1), True),
        "warning": (IngestionRunStatus.SUCCESS, now - timedelta(hours=30), True),
        "stale": (IngestionRunStatus.SUCCESS, now - timedelta(hours=100), True),
        "failing": (IngestionRunStatus.FAILED, now - timedelta(hours=2), True),
        "disabled": (IngestionRunStatus.FAILED, now - timedelta(hours=2), False),
    }
    by_name: dict[str, IngestionSource] = {}
    for name, (status, success, enabled) in specs.items():
        source = IngestionSource(
            kind=IngestionSourceKind.GREENHOUSE,
            identifier=f"inbox-{name}",
            display_name=f"Source {name}",
            enabled=enabled,
            last_success_at=success,
        )
        db.add(source)
        db.flush()
        db.add(
            IngestionRun(
                source_id=source.id,
                status=status,
                started_at=now - timedelta(minutes=5),
                finished_at=now,
            )
        )
        by_name[name] = source
    db.commit()

    warnings = {i["id"]: i for i in inbox(client)["source_warnings"]["items"]}
    assert {n for n, s in by_name.items() if str(s.id) in warnings} == {
        "warning",
        "stale",
        "failing",
    }
    assert "last run failed" in warnings[str(by_name["failing"].id)]["reason"]


# --- Program verify-by -------------------------------------------------------------------------


def test_program_verify_by_registry_only_and_window(client: TestClient, db: Session) -> None:
    source = registry_source(db)
    ids: dict[str, str] = {}
    for title, verify_by in {
        "Passed": days(-30),
        "Due today": days(0),
        "In 14": days(14),
        "In 15": days(15),
        "Hidden": days(-1),
        "Not registry": days(-1),
    }.items():
        ids[title] = make(client, title)
        set_fields(db, ids[title], verify_by=verify_by)
        if title != "Not registry":
            add_record(db, ids[title], source, OpportunitySourceType.CURATED_REGISTRY)
    hide(client, ids["Hidden"])

    section = inbox(client)["program_verify_by"]
    assert titles(section) == ["Passed", "Due today", "In 14"]
    assert section["items"][0]["reason"].startswith("Dates need re-checking")
    assert section["items"][2]["reason"].startswith("Verify dates by")


# --- Applications needing attention ------------------------------------------------------------


def track(
    client: TestClient, db: Session, title: str, status: str = "applied", **fields: Any
) -> str:
    oid = make(client, title)
    response = client.put(f"/api/opportunities/{oid}/application", json={"status": status} | fields)
    assert response.status_code == 200, response.text
    return oid


def test_applications_needing_attention(client: TestClient, db: Session) -> None:
    track(
        client, db, "Due soon", next_action="Email recruiter", next_action_due=days(3).isoformat()
    )
    track(client, db, "Overdue", next_action_due=days(-4).isoformat())
    track(client, db, "Due later", next_action_due=days(4).isoformat())
    track(client, db, "Interview soon", status="interview", interview_at=at(days(7)).isoformat())
    track(client, db, "Interview later", status="interview", interview_at=at(days(8)).isoformat())
    track(client, db, "Interview passed", status="interview", interview_at=at(days(-1)).isoformat())
    track(client, db, "Rejected but due", status="rejected", next_action_due=days(0).isoformat())
    hidden = track(client, db, "Hidden but due", next_action_due=days(0).isoformat())
    hide(client, hidden)
    stale = {
        "Stale saved": track(client, db, "Stale saved", status="saved"),
        "Stale applying": track(client, db, "Stale applying", status="applying"),
        "Stale applied": track(client, db, "Stale applied", status="applied"),
        "Fresh saved": track(client, db, "Fresh saved", status="saved"),
        "Edge saved": track(client, db, "Edge saved", status="saved"),
    }
    for title, when in {
        "Stale saved": at(days(-15)),
        "Stale applying": at(days(-30)),
        "Stale applied": at(days(-30)),  # applied is waiting on them, not on the owner
        "Fresh saved": at(days(-13)),
        "Edge saved": datetime(2041, 2, 24, tzinfo=UTC),  # exactly 14 days: not yet stale
    }.items():
        db.execute(
            update(Application)
            .where(Application.opportunity_id == stale[title])
            .values(updated_at=when)
        )
    db.commit()

    section = inbox(client)["applications"]
    assert titles(section) == [
        "Overdue",
        "Due soon",
        "Interview soon",
        "Stale applying",
        "Stale saved",
    ]
    assert section["total"] == 5
    reasons = {i["title"]: i["reason"] for i in section["items"]}
    assert reasons["Due soon"].startswith("Email recruiter (due ")
    assert reasons["Interview soon"].startswith("Interview 2041-03-17 12:00 UTC")
    assert reasons["Stale saved"].startswith("No update since")


# --- Bounded ----------------------------------------------------------------------------------


def statement_count(client: TestClient, db: Session) -> int:
    statements: list[str] = []

    def count(*args: Any) -> None:
        statements.append(args[2])

    client.get("/api/inbox", params={"today": TODAY.isoformat()})  # warm the session
    event.listen(db.get_bind(), "before_cursor_execute", count)
    try:
        assert client.get("/api/inbox", params={"today": TODAY.isoformat()}).status_code == 200
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count)
    return len(statements)


def test_inbox_statement_count_is_constant_and_sections_are_bounded(
    client: TestClient, db: Session
) -> None:
    put_profile(client)
    before = statement_count(client, db)
    source = registry_source(db)
    for n in range(inbox_service.SECTION_LIMIT + 5):
        oid = create(client, title=f"Bulk {n}", application_deadline=days(1).isoformat())["id"]
        client.put(
            f"/api/opportunities/{oid}/application",
            json={"status": "applied", "next_action_due": days(0).isoformat()},
        )
        set_fields(
            db, oid, verify_by=days(-1), first_seen_at=at(days(-1)), last_seen_at=at(days(-1))
        )
        add_record(db, oid, source, OpportunitySourceType.CURATED_REGISTRY)
    db.execute(update(OpportunityEvaluation).values(fit_score=90))
    db.commit()

    assert statement_count(client, db) == before
    body = inbox(client)
    for name in ("new_high_fit", "closing_soon", "program_verify_by", "applications"):
        assert len(body[name]["items"]) == inbox_service.SECTION_LIMIT, name
        assert body[name]["total"] == inbox_service.SECTION_LIMIT + 5, name


def test_hidden_opportunities_never_appear(client: TestClient, db: Session) -> None:
    put_profile(client)
    oid = create(client, title="Everywhere", application_deadline=days(1).isoformat())["id"]
    client.put(
        f"/api/opportunities/{oid}/application",
        json={"status": "applied", "next_action_due": days(0).isoformat()},
    )
    set_fields(db, oid, verify_by=days(-1), first_seen_at=at(days(-1)), last_seen_at=at(days(-1)))
    add_record(db, oid, registry_source(db), OpportunitySourceType.CURATED_REGISTRY)
    db.add(candidate(oid, FactReviewState.PENDING, 1))
    db.execute(update(OpportunityEvaluation).values(fit_score=90))
    db.commit()
    body = inbox(client)
    for name in (
        "new_high_fit",
        "closing_soon",
        "pending_requirement_review",
        "program_verify_by",
        "applications",
    ):
        assert titles(body[name]) == ["Everywhere"], name

    hide(client, oid)
    body = inbox(client)
    for name in (
        "new_high_fit",
        "closing_soon",
        "pending_requirement_review",
        "program_verify_by",
        "applications",
    ):
        assert body[name] == {"total": 0, "items": []}, name


def test_inbox_defaults_to_server_date_and_validates_today(client: TestClient) -> None:
    assert client.get("/api/inbox").json()["today"] == datetime.now(UTC).date().isoformat()
    assert client.get("/api/inbox", params={"today": "1999-01-01"}).status_code == 422
    assert client.get("/api/inbox", params={"today": "nope"}).status_code == 422


# --- Auth / CSRF / follow-up fields ------------------------------------------------------------


def test_inbox_requires_auth(anon_client: TestClient) -> None:
    assert anon_client.get("/api/inbox").status_code == 401


def test_application_follow_up_fields_round_trip_and_validate(
    client: TestClient, db: Session
) -> None:
    oid = make(client, "Follow up")
    path = f"/api/opportunities/{oid}/application"
    body = {
        "status": "applied",
        "next_action": "  Send thank-you note  ",
        "next_action_due": "2041-03-12",
        "interview_at": "2041-03-14T15:30:00Z",
    }
    saved = client.put(path, json=body).json()
    assert saved["next_action"] == "Send thank-you note"
    assert saved["next_action_due"] == "2041-03-12"
    assert saved["interview_at"].startswith("2041-03-14T15:30:00")
    assert client.get(f"/api/opportunities/{oid}").json()["application"]["next_action"] == (
        "Send thank-you note"
    )

    # Blank clears; explicit nulls clear (omitted fields are preserved, see below).
    cleared = client.put(
        path,
        json={
            "status": "applied",
            "next_action": "   ",
            "next_action_due": None,
            "interview_at": None,
        },
    ).json()
    assert cleared["next_action"] is None
    assert cleared["next_action_due"] is None
    assert cleared["interview_at"] is None

    assert client.put(path, json={"status": "applied", "next_action": "x" * 201}).status_code == 422
    assert (
        client.put(path, json={"status": "applied", "next_action_due": "soon"}).status_code == 422
    )
    assert db.scalars(select(Application)).one().next_action is None


@pytest.mark.parametrize("csrf", [None, "wrong-token"])
def test_application_edit_requires_csrf_and_auth(
    client: TestClient, anon_client: TestClient, csrf: str | None
) -> None:
    oid = make(client, "Guarded")
    path = f"/api/opportunities/{oid}/application"
    headers = {} if csrf is None else {"X-CSRF-Token": csrf}
    del client.headers["X-CSRF-Token"]
    body = {"status": "applied", "next_action": "Nope"}
    assert client.put(path, json=body, headers=headers).status_code == 403
    anon_client.cookies.clear()
    assert anon_client.put(path, json=body).status_code == 401


def test_interview_window_is_half_open(client: TestClient, db: Session) -> None:
    track(client, db, "Last included", status="interview", interview_at=at(days(8), 0).isoformat())
    track(client, db, "Excluded", status="interview", interview_at=at(days(9), 0).isoformat())
    last = datetime(2041, 3, 17, 23, 59, tzinfo=UTC).isoformat()
    track(client, db, "Just inside", status="interview", interview_at=last)
    track(
        client,
        db,
        "Boundary",
        status="interview",
        interview_at=datetime(2041, 3, 18, tzinfo=UTC).isoformat(),
    )
    assert titles(inbox(client)["applications"]) == ["Just inside"]


def test_application_put_preserves_omitted_follow_up_fields(client: TestClient) -> None:
    oid = make(client, "Preserve")
    path = f"/api/opportunities/{oid}/application"
    full = {
        "status": "applied",
        "next_action": "Call",
        "next_action_due": "2041-03-12",
        "interview_at": "2041-03-14T15:30:00Z",
    }
    assert client.put(path, json=full).status_code == 200
    older = client.put(path, json={"status": "interview", "notes": "n"}).json()  # older client
    assert older["status"] == "interview"
    assert older["next_action"] == "Call"
    assert older["next_action_due"] == "2041-03-12"
    assert older["interview_at"].startswith("2041-03-14T15:30")
    nulls = {
        "status": "interview",
        "next_action": None,
        "next_action_due": None,
        "interview_at": None,
    }
    cleared = client.put(path, json=nulls).json()
    assert cleared["next_action"] is None
    assert cleared["next_action_due"] is None
    assert cleared["interview_at"] is None
