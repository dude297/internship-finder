"""Opportunity list filters and sort added for Milestone 6 (ADR-012 §8, §14): requirement review
discovery and deadline search. Synthetic data only."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session

from app.models import Opportunity
from tests.test_api_requirement_review import add_candidate
from tests.test_api_workflow import create

pytestmark = pytest.mark.postgres

FIXED_TODAY = date(2041, 1, 1)


@contextmanager
def count_queries(engine: Engine) -> Generator[list[int]]:
    """A one-element list holding the number of statements executed against `engine` while the
    context is open (ADR-012 §8: the list must never scale a per-row query)."""
    counter = [0]

    def _listener(*_args: object, **_kwargs: object) -> None:
        counter[0] += 1

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _listener)


def list_ids(client: TestClient, **params: object) -> set[str]:
    response = client.get("/api/opportunities", params=params)  # type: ignore[arg-type]
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


# --- pending count / stale --------------------------------------------------------------------


def test_pending_count_and_requirements_stale_appear_in_the_list(
    client: TestClient, db: Session
) -> None:
    created = create(client)
    add_candidate(db, created["id"])
    opportunity = db.get(Opportunity, created["id"])
    assert opportunity is not None
    opportunity.requirements_stale_since = datetime.now(UTC)
    db.commit()

    items = client.get("/api/opportunities", params={"limit": 100}).json()["items"]
    item = next(i for i in items if i["id"] == created["id"])

    assert item["pending_requirement_count"] == 1
    assert item["requirements_stale"] is True


def test_requirement_review_filter(client: TestClient, db: Session) -> None:
    pending_one = create(client, title="Has Pending Candidate")
    add_candidate(db, pending_one["id"])
    stale_one = create(client, title="Is Stale")
    opportunity = db.get(Opportunity, stale_one["id"])
    assert opportunity is not None
    opportunity.requirements_stale_since = datetime.now(UTC)
    db.commit()
    create(client, title="Clean")

    assert list_ids(client, requirement_review="pending", limit=100) == {pending_one["id"]}
    assert list_ids(client, requirement_review="stale", limit=100) == {stale_one["id"]}
    assert list_ids(client, requirement_review="needs_review", limit=100) == {
        pending_one["id"],
        stale_one["id"],
    }


def test_requirements_assessment_status_filter(client: TestClient) -> None:
    complete_one = create(client, requirements_assessment_status="complete")
    unassessed_one = create(client)

    ids = list_ids(client, requirements_assessment_status="complete", limit=100)

    assert complete_one["id"] in ids
    assert unassessed_one["id"] not in ids


# --- deadlines (ADR-012 §14) -------------------------------------------------------------------


def test_deadline_within_and_has_deadline_filters(client: TestClient) -> None:
    today = FIXED_TODAY
    ids = {
        "today": create(client, application_deadline=today.isoformat())["id"],
        "plus5": create(client, application_deadline=(today + timedelta(days=5)).isoformat())["id"],
        "plus10": create(client, application_deadline=(today + timedelta(days=10)).isoformat())[
            "id"
        ],
        "plus40": create(client, application_deadline=(today + timedelta(days=40)).isoformat())[
            "id"
        ],
        "past": create(client, application_deadline=(today - timedelta(days=1)).isoformat())["id"],
        "none": create(client, application_deadline=None)["id"],
    }

    within7 = list_ids(client, deadline_within=7, today=today.isoformat(), limit=100)
    assert within7 == {ids["today"], ids["plus5"]}

    within14 = list_ids(client, deadline_within=14, today=today.isoformat(), limit=100)
    assert within14 == {ids["today"], ids["plus5"], ids["plus10"]}

    within30 = list_ids(client, deadline_within=30, today=today.isoformat(), limit=100)
    assert within30 == {ids["today"], ids["plus5"], ids["plus10"]}
    assert ids["plus40"] not in within30
    assert ids["past"] not in within30
    assert ids["none"] not in within30

    has_deadline = list_ids(client, has_deadline=True, limit=100)
    assert ids["none"] not in has_deadline
    assert ids["today"] in has_deadline

    no_deadline = list_ids(client, has_deadline=False, limit=100)
    assert no_deadline == {ids["none"]}


def test_deadline_within_defaults_to_server_utc_date(client: TestClient) -> None:
    today = datetime.now(UTC).date()
    created = create(client, application_deadline=today.isoformat())

    within7 = list_ids(client, deadline_within=7, limit=100)

    assert created["id"] in within7


def test_sort_deadline_orders_ascending_with_nulls_last(client: TestClient) -> None:
    mid = create(client, title="Mid Deadline", application_deadline="2041-01-15")
    none = create(client, title="No Deadline", application_deadline=None)
    early = create(client, title="Early Deadline", application_deadline="2041-01-01")

    response = client.get("/api/opportunities", params={"sort": "deadline", "limit": 100})
    order = [item["id"] for item in response.json()["items"]]

    assert order.index(early["id"]) < order.index(mid["id"]) < order.index(none["id"])


# --- pagination ------------------------------------------------------------------------------


def test_pagination_and_total_are_correct_with_filters(client: TestClient) -> None:
    matching = [
        create(client, title=f"Complete {i}", requirements_assessment_status="complete")["id"]
        for i in range(5)
    ]
    create(client, title="Unassessed")  # excluded by the filter

    page1 = client.get(
        "/api/opportunities",
        params={"requirements_assessment_status": "complete", "limit": 2, "offset": 0},
    ).json()
    page2 = client.get(
        "/api/opportunities",
        params={"requirements_assessment_status": "complete", "limit": 2, "offset": 2},
    ).json()
    page3 = client.get(
        "/api/opportunities",
        params={"requirements_assessment_status": "complete", "limit": 2, "offset": 4},
    ).json()

    assert page1["total"] == page2["total"] == page3["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert len(page3["items"]) == 1
    seen = {i["id"] for page in (page1, page2, page3) for i in page["items"]}
    assert seen == set(matching)


# --- query count (no N+1) -------------------------------------------------------------------


def test_listing_does_not_scale_queries_with_item_count(
    client: TestClient, db: Session, pg_engine: Engine
) -> None:
    for i in range(5):
        create(client, title=f"Small {i}")
    with count_queries(pg_engine) as small:
        response = client.get("/api/opportunities", params={"limit": 50})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 5

    for i in range(45):
        create(client, title=f"Large {i}")
    with count_queries(pg_engine) as large:
        response = client.get("/api/opportunities", params={"limit": 50})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 50

    assert small[0] == large[0]
