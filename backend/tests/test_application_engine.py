"""Application engine v2 and the home dashboard (ADR-025). Synthetic data only.

`today` is pinned (2041-03-10) so every date window is deterministic."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.enums import ApplicationStatus as S
from app.models import Application, ApplicationEvent, Opportunity
from app.schemas.application import ApplicationBody
from app.services import opportunities as opportunity_service
from tests.test_api_workflow import create

pytestmark = pytest.mark.postgres

TODAY = date(2041, 3, 10)


def days(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def at(day: date, hour: int = 12) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def make(client: TestClient, title: str = "Role", org: str = "Example Org") -> str:
    return create(client, title=title, organization=org, application_deadline=None)["id"]


def track(client: TestClient, oid: str, **body: Any) -> dict[str, Any]:
    if "status" not in body:  # the API requires a status; keep the current one
        body["status"] = client.get(f"/api/opportunities/{oid}").json()["application"]["status"]
    response = client.put(f"/api/opportunities/{oid}/application", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def events(client: TestClient, application_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/api/applications/{application_id}/events")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def kinds(client: TestClient, application_id: str) -> list[str]:
    return [e["event_type"] for e in events(client, application_id)]


# --- Events ---------------------------------------------------------------------------------


def test_lifecycle_writes_events_in_order(client: TestClient) -> None:
    oid = make(client)
    app = track(client, oid, status="saved")
    track(client, oid, status="applying")
    track(client, oid, status="applied")
    track(client, oid, next_action="Email recruiter", next_action_due=days(5))
    track(client, oid, status="interview", interview_at="2041-03-20T15:00:00Z")
    track(client, oid, status="offer")
    track(client, oid, status="accepted")
    assert kinds(client, app["id"]) == [
        "created",
        "status_changed",
        "status_changed",
        "next_action_changed",
        "deadline_changed",
        "status_changed",
        "interview_scheduled",
        "status_changed",
        "offer_received",
        "status_changed",
    ]
    statuses = [(e["from_status"], e["to_status"]) for e in events(client, app["id"])]
    assert ("offer", "accepted") in statuses and (None, "saved") in statuses


def test_no_op_put_writes_no_event(client: TestClient) -> None:
    oid = make(client)
    app = track(client, oid, status="applying", next_action="Draft essay", notes="hello")
    before = events(client, app["id"])
    track(client, oid, status="applying", next_action="Draft essay", notes="hello")
    track(client, oid, status="applying")
    assert events(client, app["id"]) == before


def test_submitted_on_alone_is_not_meaningful(client: TestClient) -> None:
    oid = make(client)
    app = track(client, oid, status="applying")
    track(client, oid, status="applying", submitted_on=days(-1))
    assert kinds(client, app["id"]) == ["created"]


def test_events_share_the_callers_transaction(client: TestClient, db: Session) -> None:
    opp = db.get(Opportunity, make(client))
    assert opp is not None
    savepoint = db.begin_nested()
    opportunity_service.save_application(db, opp, ApplicationBody(status=S.APPLIED))
    assert (
        db.scalar(select(func.count()).select_from(ApplicationEvent)) == 1
    )  # `created` only; a new application's status isn't a change
    savepoint.rollback()
    assert db.scalar(select(func.count()).select_from(ApplicationEvent)) == 0
    assert db.scalar(select(func.count()).select_from(Application)) == 0


def test_interview_events_keep_every_change(client: TestClient) -> None:
    oid = make(client)
    app = track(client, oid, status="interview", interview_at="2041-03-20T15:00:00Z")
    track(client, oid, interview_at="2041-03-22T15:00:00Z")
    track(client, oid, interview_at="2041-03-25T09:30:00+00:00")
    track(client, oid, interview_at=None)
    found = events(client, app["id"])
    assert [e["event_type"] for e in found] == [
        "created",
        "interview_scheduled",
        "interview_updated",
        "interview_updated",
        "interview_updated",
    ]
    assert found[-1]["metadata_json"]["to"] is None


def test_notes_event_never_stores_the_note(client: TestClient) -> None:
    oid = make(client)
    app = track(client, oid, status="saved")
    track(client, oid, notes="secret thoughts")
    track(client, oid, notes=None)  # clearing a note is not "added"
    found = events(client, app["id"])
    assert [e["event_type"] for e in found] == ["created", "note_added"]
    assert "secret" not in str(found[1]["metadata_json"])


def test_next_action_text_and_due_date_are_separate_events(client: TestClient) -> None:
    oid = make(client)
    app = track(client, oid, status="applied", next_action="Follow up", next_action_due=days(3))
    track(client, oid, next_action_due=days(7))
    found = events(client, app["id"])
    assert [e["event_type"] for e in found] == [
        "created",
        "next_action_changed",
        "deadline_changed",
        "deadline_changed",
    ]
    assert found[-1]["metadata_json"] == {"from": days(3), "to": days(7)}


def test_deleting_the_application_removes_its_events(client: TestClient, db: Session) -> None:
    oid = make(client)
    track(client, oid, status="applied")
    assert client.delete(f"/api/opportunities/{oid}/application").status_code == 204
    assert db.scalar(select(func.count()).select_from(ApplicationEvent)) == 0


def test_legacy_application_has_no_events_and_no_invented_history(
    client: TestClient, db: Session
) -> None:
    oid = make(client)
    legacy = Application(opportunity_id=oid, status=S.APPLIED)  # as a pre-ADR-025 row
    db.add(legacy)
    db.commit()
    assert events(client, str(legacy.id)) == []
    track(client, oid, status="interview")
    assert kinds(client, str(legacy.id)) == ["status_changed"]  # no fabricated `created`
    assert (
        client.get("/api/applications/00000000-0000-0000-0000-000000000000/events").status_code
        == 404
    )


# --- applied_at -----------------------------------------------------------------------------


def test_applied_at_is_stamped_once_on_first_applied(client: TestClient) -> None:
    oid = make(client)
    assert track(client, oid, status="applying")["applied_at"] is None
    first = track(client, oid, status="applied")["applied_at"]
    assert first is not None
    track(client, oid, status="interview")
    assert track(client, oid, status="applied")["applied_at"] == first  # not re-stamped


def test_manual_applied_at_is_preserved_and_correctable(client: TestClient) -> None:
    oid = make(client)
    manual = "2041-02-01T00:00:00Z"
    assert track(client, oid, status="applied", applied_at=manual)["applied_at"].startswith(
        "2041-02-01"
    )
    track(client, oid, status="rejected")
    assert track(client, oid, status="applied")["applied_at"].startswith("2041-02-01")
    corrected = track(client, oid, applied_at="2041-02-03T00:00:00Z")
    assert corrected["applied_at"].startswith("2041-02-03")


def test_applied_at_must_be_plausible(client: TestClient) -> None:
    oid = make(client)
    response = client.put(
        f"/api/opportunities/{oid}/application",
        json={"status": "applied", "applied_at": "1999-01-01T00:00:00Z"},
    )
    assert response.status_code == 422


def test_any_transition_is_allowed(client: TestClient) -> None:
    oid = make(client)
    for status in ("accepted", "saved", "withdrawn", "applied", "rejected", "interview"):
        assert track(client, oid, status=status)["status"] == status


# --- List and pipeline -----------------------------------------------------------------------


def test_list_filters_sorts_and_overdue(client: TestClient) -> None:
    a = make(client, "Alpha role", "Zeta Labs")
    b = make(client, "Beta role", "Acme Corp")
    c = make(client, "Gamma role", "Middle Inc")
    track(client, a, status="applied", next_action_due=days(-1))  # overdue
    track(client, b, status="interview", interview_at="2041-03-12T10:00:00Z")
    track(client, c, status="applying", next_action_due=days(0))  # due today: not overdue
    track(client, make(client, "Done", "Zed"), status="rejected", next_action_due=days(-9))

    def query(**params: Any) -> list[dict[str, Any]]:
        response = client.get("/api/applications", params={"today": TODAY.isoformat()} | params)
        assert response.status_code == 200, response.text
        return response.json()["items"]

    overdue = query(follow_up_overdue=True)
    assert [i["title"] for i in overdue] == ["Alpha role"]  # rejected is finished, not overdue
    assert [i["title"] for i in query(due_soon=True)] == ["Gamma role"]  # today counts
    assert [i["title"] for i in query(interview_upcoming=True)] == ["Beta role"]
    assert [i["title"] for i in query(stage=["applied", "interview"], sort="company")] == [
        "Beta role",
        "Alpha role",
    ]
    assert [i["title"] for i in query(company="acme")] == ["Beta role"]
    assert [i["title"] for i in query(sort="stage")][:3] == [
        "Gamma role",
        "Alpha role",
        "Beta role",
    ]
    assert query(sort="company")[0]["organization"] == "Acme Corp"
    assert query(sort="interview")[0]["title"] == "Beta role"
    assert query(sort="applied")[0]["title"] == "Alpha role"
    assert len(query(sort="newest")) == 4  # created_at ties inside one test transaction
    assert query(sort="next_action")[0]["title"] == "Done"  # earliest due date first
    page = client.get("/api/applications", params={"limit": 1, "offset": 9}).json()
    assert page["items"] == [] and page["total"] == 4
    assert client.get("/api/applications", params={"stage": "nope"}).status_code == 422


# --- Stale-write protection ------------------------------------------------------------------


def put(client: TestClient, oid: str, body: dict[str, Any]) -> Any:
    return client.put(f"/api/opportunities/{oid}/application", json=body)


def test_status_is_optional_and_omitted_means_unchanged(client: TestClient) -> None:
    oid = make(client)
    assert put(client, oid, {}).json()["status"] == "saved"  # new application defaults to saved
    track(client, oid, status="interview")
    response = put(client, oid, {"next_action": "Thank-you note", "next_action_due": days(2)})
    assert response.status_code == 200 and response.json()["status"] == "interview"
    assert put(client, oid, {"status": None}).status_code == 422


def test_expected_updated_at_guards_against_stale_screens(client: TestClient, db: Session) -> None:
    oid = make(client)
    first = put(client, oid, {"status": "applying"}).json()
    ok = put(client, oid, {"status": "applied", "expected_updated_at": first["updated_at"]})
    assert ok.status_code == 200
    # One test transaction shares a single now(); make the row's updated_at move as it would.
    db.execute(update(Application).values(updated_at=at(TODAY)))
    db.commit()
    stale = put(client, oid, {"status": "rejected", "expected_updated_at": first["updated_at"]})
    assert stale.status_code == 409 and "Reload" in stale.json()["detail"]
    assert client.get(f"/api/opportunities/{oid}").json()["application"]["status"] == "applied"
    # Deleted elsewhere: a stage change must not recreate it.
    assert client.delete(f"/api/opportunities/{oid}/application").status_code == 204
    gone = put(client, oid, {"status": "applied", "expected_updated_at": ok.json()["updated_at"]})
    assert gone.status_code == 409
    assert client.get(f"/api/opportunities/{oid}").json()["application"] is None


def test_next_action_event_never_stores_the_text(client: TestClient) -> None:
    oid = make(client)
    app = track(client, oid, status="applied", next_action="Call Dana at the lab")
    found = [e for e in events(client, app["id"]) if e["event_type"] == "next_action_changed"]
    assert found and found[0]["metadata_json"] == {"length": len("Call Dana at the lab")}
    assert "Dana" not in str(events(client, app["id"]))
