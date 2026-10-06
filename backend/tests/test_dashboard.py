"""Home dashboard (ADR-025). Synthetic data only. `today` is pinned (2041-03-10)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from app.enums import ApplicationStatus as S
from app.enums import IngestionSourceKind, OpportunitySourceType, SourceRegion, SourceScope
from app.models import (
    Application,
    ApplicationEvent,
    IngestionSource,
    Opportunity,
    OpportunityEvaluation,
    OpportunitySourceRecord,
)
from app.services import dashboard as dashboard_service
from tests.test_api_workflow import create, put_profile
from tests.test_application_engine import TODAY, at, days, make, track
from tests.test_source_discovery import ats_source, gh_fields, make_opportunity, make_record

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
    assert before <= 22  # was 20 before the two new-supply statements (ADR-025 amendment)
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


def dash(client: TestClient, offset: int = 0) -> dict[str, Any]:
    response = client.get(
        "/api/dashboard", params={"today": TODAY.isoformat(), "tz_offset_minutes": offset}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_interview_days_follow_the_clients_time_zone(client: TestClient) -> None:
    # 19:00 on 2041-03-10 in UTC-8 is already 03:00 on the 11th in UTC.
    track(client, make(client, "Evening"), status="interview", interview_at="2041-03-11T03:00:00Z")
    # 06:00 on 2041-03-10 in UTC+10 is still the 9th in UTC.
    track(client, make(client, "Morning"), status="interview", interview_at="2041-03-09T20:00:00Z")

    def days_by_title(offset: int) -> dict[str, str]:
        return {
            t["title"]: t["date"]
            for t in dash(client, offset)["upcoming"]
            if t["kind"] == "interview"
        }

    assert days_by_title(480)["Evening"] == "2041-03-10"  # US Pacific
    assert days_by_title(0)["Evening"] == "2041-03-11"
    assert days_by_title(-600)["Morning"] == "2041-03-10"  # UTC+10: today in local time
    assert "Morning" not in days_by_title(0)  # before UTC midnight of `today`
    # The list's "interview upcoming" starts at the client's local midnight as well.
    pacific = client.get(
        "/api/applications",
        params={"today": TODAY.isoformat(), "tz_offset_minutes": 480, "interview_upcoming": True},
    ).json()["items"]
    assert [i["title"] for i in pacific] == ["Evening"]  # Morning (Mar 9 UTC) is before 08:00Z
    assert client.get("/api/dashboard", params={"tz_offset_minutes": 900}).status_code == 422


def test_timeline_kinds_do_not_starve_each_other(client: TestClient) -> None:
    for n in range(dashboard_service.UPCOMING_LIMIT * 2 + 1):
        track(client, make(client, f"Due{n}"), status="applied", next_action_due=days(1))
    track(
        client,
        make(client, "Tomorrow call"),
        status="interview",
        interview_at="2041-03-11T09:00:00Z",
    )
    track(client, make(client, "Far call"), status="interview", interview_at="2041-06-20T09:00:00Z")
    titles = [t["title"] for t in dash(client)["upcoming"]]
    assert "Tomorrow call" in titles
    assert "Far call" not in titles


def test_past_verify_by_dates_do_not_take_timeline_slots(client: TestClient, db: Session) -> None:
    put_profile(client)
    for n in range(12):
        create(client, title=f"Past{n}", application_deadline=None)
    db.execute(update(Opportunity).values(verify_by=TODAY - timedelta(days=3)))
    db.commit()
    create(client, title="Soon", application_deadline=days(2))
    assert [t["title"] for t in dash(client)["upcoming"]] == ["Soon"]


def test_funnel_stages_are_nested_and_rates_never_exceed_one(client: TestClient) -> None:
    for n in range(6):  # accepted with no recorded history at all
        track(client, make(client, f"A{n}"), status="accepted")
    funnel = dash(client)["funnel"]
    assert funnel["applied"] >= funnel["interviewed"] >= funnel["offered"] >= funnel["accepted"]
    assert funnel["accepted"] == 6 and funnel["applied"] == 6
    for key in ("applied_to_interview_rate", "interview_to_offer_rate", "offer_to_accepted_rate"):
        assert funnel[key] == 1.0


def test_actions_total_counts_an_opportunity_once(client: TestClient) -> None:
    oid = create(client, title="Both", application_deadline=days(2))["id"]
    track(client, oid, status="applied", next_action_due=days(-1))  # also a follow-up action
    body = dash(client)
    assert body["actions"]["closing_soon"]["total"] == 1
    assert body["actions"]["applications"]["total"] == 1
    assert body["actions"]["total"] == 1


# --- New supply (ADR-025 amendment): first_seen_at based, hidden excluded -----------------------


def _new(db: Session, seen: datetime, *, source: IngestionSource | None = None, **kw: Any) -> str:
    opp = make_opportunity(db, title=f"New {seen.isoformat()}")
    opp.first_seen_at = opp.last_seen_at = seen
    if source is not None:
        ext, url = gh_fields(job=str(opp.id)[:8])
        make_record(
            db,
            opp,
            source=source,
            external_id=ext,
            source_url=url,
            source_type=kw.get("source_type", OpportunitySourceType.PUBLIC_FEED),
        )
    db.commit()
    return str(opp.id)


def _discovery(client: TestClient, offset: int = 0) -> dict[str, Any]:
    r = client.get(
        "/api/dashboard", params={"today": TODAY.isoformat(), "tz_offset_minutes": offset}
    )
    assert r.status_code == 200, r.text
    return r.json()["discovery"]


def test_new_supply_zero_data(client: TestClient) -> None:
    d = _discovery(client)
    assert (d["new_today"], d["new_this_week"], d["new_this_week_independent"]) == (0, 0, 0)
    assert d["new_this_week_by_provider"] == [] and d["closing_soon"] == 0
    assert [w["count"] for w in d["weekly_new"]] == [0] * 8
    assert d["weekly_new"][-1]["week_start"] == "2041-03-04"
    assert d["weekly_new"][0]["week_start"] == "2041-01-14"


def test_new_supply_week_boundaries_and_time_zone(client: TestClient, db: Session) -> None:
    _new(db, datetime(2041, 3, 10, 0, 0, tzinfo=UTC))  # today
    _new(db, datetime(2041, 3, 4, 0, 0, tzinfo=UTC))  # first instant of the week
    _new(db, datetime(2041, 3, 3, 23, 59, tzinfo=UTC))  # last instant of the previous week
    _new(db, datetime(2041, 1, 14, 0, 0, tzinfo=UTC))  # first instant of the 8-week trend
    _new(db, datetime(2041, 1, 13, 23, 59, tzinfo=UTC))  # before the trend: never counted
    _new(db, datetime(2041, 3, 11, 0, 0, tzinfo=UTC))  # UTC tomorrow: not counted at offset 0
    d = _discovery(client)
    assert (d["new_today"], d["new_this_week"]) == (1, 2)
    assert [w["count"] for w in d["weekly_new"]] == [1, 0, 0, 0, 0, 0, 1, 2]
    # Browser at UTC-8 (+480): local today starts 08:00 UTC, so the 03-10 00:00 UTC opportunity
    # is local yesterday (still this week); the 03-11 00:00 UTC one is local 03-10 16:00: today.
    d = _discovery(client, 480)
    assert (d["new_today"], d["new_this_week"]) == (1, 2)  # 03-04 00:00 UTC is local 03-03


def test_new_supply_closed_and_hidden(client: TestClient, db: Session) -> None:
    source = ats_source(db, IngestionSourceKind.GREENHOUSE, "acme")
    seen = datetime(2041, 3, 9, 12, tzinfo=UTC)
    closed = _new(db, seen, source=source)
    hidden = _new(db, seen, source=source)
    _new(db, seen, source=source)
    for rec in db.scalars(
        select(OpportunitySourceRecord).where(
            OpportunitySourceRecord.opportunity_id == uuid.UUID(closed)
        )
    ):
        rec.is_active = False
        rec.closed_at = seen
    db.commit()
    assert client.put(f"/api/opportunities/{hidden}/dismissal").status_code == 200
    d = _discovery(client)
    assert d["new_this_week"] == 1  # closed and hidden are not open
    assert d["weekly_new"][-1]["count"] == 2  # trend keeps the closed one; hidden is excluded
    assert d["new_this_week_by_provider"] == [{"provider": "greenhouse", "count": 1}]


def test_new_supply_feed_only_vs_independent(client: TestClient, db: Session) -> None:
    gh = ats_source(db, IngestionSourceKind.GREENHOUSE, "acme")
    feed = _builtin(db, IngestionSourceKind.COMMUNITY_FEED)
    seen = datetime(2041, 3, 9, 12, tzinfo=UTC)
    _new(db, seen, source=feed)  # feed only
    _new(db, seen, source=gh, source_type=OpportunitySourceType.ATS)  # independent
    both = _new(db, seen, source=feed)  # feed + ATS: independent
    opp = db.get(Opportunity, uuid.UUID(both))
    assert opp is not None
    ext, url = gh_fields(job="9999")
    make_record(
        db, opp, source=gh, external_id=ext, source_url=url, source_type=OpportunitySourceType.ATS
    )
    db.commit()
    d = _discovery(client)
    assert (d["new_this_week"], d["new_this_week_independent"]) == (3, 2)
    assert {p["provider"]: p["count"] for p in d["new_this_week_by_provider"]} == {
        "community_feed": 2,
        "greenhouse": 2,
    }


def test_new_supply_provider_list_is_top_five(client: TestClient, db: Session) -> None:
    seen = datetime(2041, 3, 9, 12, tzinfo=UTC)
    for i, kind in enumerate(list(IngestionSourceKind)[:6]):
        _new(db, seen, source=_builtin(db, kind, f"id{i}"))
    assert len(_discovery(client)["new_this_week_by_provider"]) == 5


def _builtin(db: Session, kind: IngestionSourceKind, ident: str = "x") -> IngestionSource:
    builtin = kind in (IngestionSourceKind.COMMUNITY_FEED, IngestionSourceKind.CURATED_REGISTRY)
    src = IngestionSource(
        kind=kind,
        identifier=ident,
        region=SourceRegion.GLOBAL if kind == IngestionSourceKind.LEVER else None,
        display_name="Synthetic",
        scope=SourceScope.ALL if builtin else SourceScope.INTERNSHIPS_ONLY,
    )
    db.add(src)
    db.flush()
    return src
