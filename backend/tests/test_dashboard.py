"""Home dashboard (ADR-025). Synthetic data only. `today` is pinned (2041-03-10)."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, update
from sqlalchemy.orm import Session

from app.enums import ApplicationStatus as S
from app.models import Application, ApplicationEvent, Opportunity, OpportunityEvaluation
from app.services import dashboard as dashboard_service
from tests.test_api_workflow import create, put_profile
from tests.test_application_engine import TODAY, at, days, make, track

pytestmark = pytest.mark.postgres


def recent(db: Session) -> None:
    seen = at(TODAY - timedelta(days=1))
    db.execute(update(Opportunity).values(first_seen_at=seen, last_seen_at=seen))


def dashboard(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/dashboard", params={"today": TODAY.isoformat()})
    assert response.status_code == 200, response.text
    return response.json()


# --- Dashboard ------------------------------------------------------------------------------


def test_dashboard_empty_has_null_rates_and_no_nan(client: TestClient) -> None:
    body = dashboard(client)
    funnel = body["funnel"]
    assert funnel["applied"] == 0
    for key in (
        "applied_to_interview_rate",
        "interview_to_offer_rate",
        "offer_to_accepted_rate",
        "median_days_to_interview",
        "median_days_to_rejection",
        "median_days_to_offer",
    ):
        assert funnel[key] is None, key
    assert body["pipeline"] == {s.value: 0 for s in S}
    assert body["actions"]["total"] == 0
    assert body["discovery"]["independent_percent"] is None
    assert client.get("/api/dashboard", params={"today": "1900-01-01"}).status_code == 422


def test_rates_need_five_applications(client: TestClient) -> None:
    for i in range(4):
        track(client, make(client, f"R{i}"), status="interview")
    assert dashboard(client)["funnel"]["applied_to_interview_rate"] is None
    track(client, make(client, "R4"), status="applied")
    funnel = dashboard(client)["funnel"]
    assert funnel["applied"] == 5 and funnel["interviewed"] == 4
    assert funnel["applied_to_interview_rate"] == 0.8
    assert funnel["interview_to_offer_rate"] is None  # only 4 interviewed


def test_rejected_or_withdrawn_before_interview_are_counted_separately(
    client: TestClient,
) -> None:
    track(client, make(client, "early reject"), status="applied")
    track(client, make(client, "early reject"), status="rejected")
    late = make(client, "late reject")
    track(client, late, status="interview", interview_at="2041-03-20T15:00:00Z")
    track(client, late, status="rejected")  # interviewed first: history keeps it in the funnel
    track(client, make(client, "early withdraw"), status="withdrawn")
    funnel = dashboard(client)["funnel"]
    assert funnel["rejected_before_interview"] == 1
    assert funnel["withdrawn_before_interview"] == 1
    assert funnel["interviewed"] == 1


def test_median_days_need_three_timed_applications(client: TestClient, db: Session) -> None:
    ids: list[str] = []
    for i, gap in enumerate((2, 4, 10)):
        app = track(client, make(client, f"T{i}"), status="applied")
        ids.append(app["id"])
        applied = at(TODAY - timedelta(days=30))
        db.execute(
            update(Application).where(Application.id == app["id"]).values(applied_at=applied)
        )
        db.commit()
        track(client, str(app["opportunity_id"]), status="interview")
        db.execute(
            update(ApplicationEvent)
            .where(
                ApplicationEvent.application_id == app["id"],
                ApplicationEvent.to_status == S.INTERVIEW,
            )
            .values(occurred_at=applied + timedelta(days=gap))
        )
        db.commit()
        if i == 1:
            assert dashboard(client)["funnel"]["median_days_to_interview"] is None  # 2 samples
    assert dashboard(client)["funnel"]["median_days_to_interview"] == 4.0
    assert dashboard(client)["funnel"]["median_days_to_offer"] is None


def test_dashboard_actions_and_hidden_exclusion(client: TestClient, db: Session) -> None:
    put_profile(client)
    due = make(client, "Follow-up due")
    track(client, due, status="applied", next_action="Email", next_action_due=days(-2))
    hidden = make(client, "Hidden one")
    track(client, hidden, status="applied", next_action="Email", next_action_due=days(-2))
    fit = create(client, title="High fit", application_deadline=days(3))["id"]
    hidden_fit = create(client, title="Hidden fit", application_deadline=days(3))["id"]
    db.execute(update(OpportunityEvaluation).values(fit_score=90, eligibility_status="eligible"))
    recent(db)
    db.commit()
    assert client.put(f"/api/opportunities/{hidden}/dismissal").status_code == 200
    assert client.put(f"/api/opportunities/{hidden_fit}/dismissal").status_code == 200

    body = dashboard(client)
    actions = body["actions"]["applications"]["items"]
    assert [i["title"] for i in actions] == ["Follow-up due"]
    assert actions[0]["kind"] == "follow_up_overdue"
    assert [i["title"] for i in body["actions"]["closing_soon"]["items"]] == ["High fit"]
    assert [i["id"] for i in body["high_fit_new"]["items"]] == [fit]
    assert body["pipeline"]["applied"] == 2  # the pipeline counts applications, hidden or not
    kinds_ = [(t["kind"], t["title"]) for t in body["upcoming"]]
    assert ("deadline", "High fit") in kinds_ and all("Hidden" not in t for _, t in kinds_)


def test_high_fit_excludes_tracked_ineligible_and_low_fit(client: TestClient, db: Session) -> None:
    put_profile(client)
    ids = {n: create(client, title=n, application_deadline=None)["id"] for n in "ABCD"}
    for n, (fit, status) in {
        "A": (95, "needs_verification"),
        "B": (80, "eligible"),
        "C": (99, "ineligible"),
        "D": (40, "eligible"),
    }.items():
        db.execute(
            update(OpportunityEvaluation)
            .where(OpportunityEvaluation.opportunity_id == ids[n])
            .values(fit_score=fit, eligibility_status=status)
        )
    recent(db)
    db.commit()
    # Eligible first even with a lower fit; ineligible and low fit never appear.
    assert [i["title"] for i in dashboard(client)["high_fit_new"]["items"]] == ["B", "A"]
    track(client, ids["B"], status="applied")
    assert [i["title"] for i in dashboard(client)["high_fit_new"]["items"]] == ["A"]


def test_stale_applied_and_interview_window(client: TestClient, db: Session) -> None:
    stale = make(client, "Stale applied")
    track(client, stale, status="applied")
    track(
        client,
        make(client, "Interview soon"),
        status="interview",
        interview_at="2041-03-12T10:00:00Z",
    )
    track(
        client,
        make(client, "Interview far"),
        status="interview",
        interview_at="2041-04-30T10:00:00Z",
    )
    db.execute(update(Application).values(updated_at=at(TODAY - timedelta(days=30))))
    db.commit()
    items = dashboard(client)["actions"]["applications"]["items"]
    by_title = {i["title"]: i["kind"] for i in items}
    assert by_title["Stale applied"] == "stale"
    assert by_title["Interview soon"] == "interview"  # also stale, but the interview wins
    assert "Interview far" not in by_title  # outside the window, and not an applying/applied row


def test_upcoming_is_chronological_and_bounded(client: TestClient) -> None:
    for n in range(dashboard_service.UPCOMING_LIMIT + 4):
        track(
            client,
            make(client, f"U{n}"),
            status="applied",
            next_action_due=days(1 + n % 10),
        )
    track(client, make(client, "Call"), status="interview", interview_at="2041-03-10T09:00:00Z")
    upcoming = dashboard(client)["upcoming"]
    assert len(upcoming) == dashboard_service.UPCOMING_LIMIT
    keys = [t["at"] or f"{t['date']}T00:00:00Z" for t in upcoming]
    assert keys == sorted(keys)
    assert upcoming[0]["kind"] == "interview" and upcoming[0]["at"] is not None


def test_dashboard_statement_count_is_constant(client: TestClient, db: Session) -> None:
    put_profile(client)

    def count() -> int:
        statements: list[str] = []

        def record(*args: Any) -> None:
            statements.append(args[2])

        dashboard(client)  # warm the session
        event.listen(db.get_bind(), "before_cursor_execute", record)
        try:
            dashboard(client)
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", record)
        return len(statements)

    before = count()
    for n in range(15):
        oid = create(client, title=f"Bulk {n}", application_deadline=days(2))["id"]
        track(
            client,
            oid,
            status="interview",
            next_action_due=days(-1),
            interview_at="2041-03-12T10:00:00Z",
        )
    db.execute(update(OpportunityEvaluation).values(fit_score=90, eligibility_status="eligible"))
    db.commit()
    assert count() == before
    assert before <= 30
    body = dashboard(client)
    assert len(body["actions"]["applications"]["items"]) <= 10
    assert body["actions"]["applications"]["total"] == 15


def test_legacy_application_counts_in_pipeline_and_funnel(client: TestClient, db: Session) -> None:
    legacy = Application(opportunity_id=make(client), status=S.APPLIED)  # pre-ADR-025 row
    db.add(legacy)
    db.commit()
    body = dashboard(client)
    assert body["pipeline"]["applied"] == 1
    assert body["funnel"]["applied"] == 1
    assert body["funnel"]["median_days_to_interview"] is None
