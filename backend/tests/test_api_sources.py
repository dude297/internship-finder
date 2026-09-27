"""Sources API, sync through the API, discovery list (pagination/filters), provenance on the
detail page, and the manual review of imported opportunities. Synthetic data only."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.adapters.community_feed import BUILTIN_IDENTIFIER
from app.ingestion.http import configured_transport
from app.models import IngestionRun, IngestionSource, OpportunityEvaluation
from tests.ingestion_fixtures import (
    FEED_URL,
    GREENHOUSE_BOARD,
    GREENHOUSE_URL,
    LEVER_SITE,
    FakeSource,
    feed,
    feed_job,
    greenhouse_board,
    greenhouse_job,
)
from tests.test_api_workflow import AGE_16, INCOMING_UNDERGRAD, create, opportunity, put_profile

pytestmark = pytest.mark.postgres


@pytest.fixture
def web(client: TestClient) -> Iterator[FakeSource]:
    fake = FakeSource()
    app: FastAPI = client.app  # pyright: ignore[reportAssignmentType]
    app.dependency_overrides[configured_transport] = fake.transport
    yield fake
    app.dependency_overrides.pop(configured_transport, None)


def builtin(client: TestClient) -> dict[str, Any]:
    return next(s for s in client.get("/api/sources").json() if s["builtin"])


def add_greenhouse(client: TestClient, board: str = GREENHOUSE_BOARD) -> dict[str, Any]:
    response = client.post(
        "/api/sources",
        json={"kind": "greenhouse", "display_name": "Example Robotics", "board": board},
    )
    assert response.status_code == 201, response.text
    return response.json()


def sync(client: TestClient, source_id: str) -> dict[str, Any]:
    response = client.post(f"/api/sources/{source_id}/sync")
    assert response.status_code == 200, response.text
    return response.json()


def page(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/opportunities", params=params)
    assert response.status_code == 200, response.text
    return response.json()


# --- Registry -----------------------------------------------------------------------------------


def test_the_builtin_feed_is_listed(client: TestClient) -> None:
    [source] = client.get("/api/sources").json()

    assert source["kind"] == "community_feed"
    assert source["identifier"] == BUILTIN_IDENTIFIER
    assert source["display_name"] == "Tech Internship Discovery Feed"
    assert source["builtin"] is True and source["enabled"] is True
    assert source["latest_run"] is None
    assert "url" not in source  # no endpoint is exposed or configurable


@pytest.mark.parametrize(
    ("body", "identifier", "region"),
    [
        (
            {"kind": "greenhouse", "board": "https://job-boards.greenhouse.io/ExampleRobotics"},
            "examplerobotics",
            None,
        ),
        ({"kind": "greenhouse", "board": "examplerobotics"}, "examplerobotics", None),
        ({"kind": "lever", "board": f"https://jobs.eu.lever.co/{LEVER_SITE}"}, LEVER_SITE, "eu"),
        ({"kind": "lever", "board": LEVER_SITE}, LEVER_SITE, "global"),
        ({"kind": "lever", "board": LEVER_SITE, "region": "eu"}, LEVER_SITE, "eu"),
    ],
)
def test_sources_are_added_from_provider_links(
    client: TestClient, body: dict[str, Any], identifier: str, region: str | None
) -> None:
    response = client.post("/api/sources", json={"display_name": "Example", **body})

    assert response.status_code == 201, response.text
    created = response.json()
    assert (created["identifier"], created["region"], created["builtin"]) == (
        identifier,
        region,
        False,
    )


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "greenhouse", "board": "https://evil.example/examplerobotics"},
        {"kind": "greenhouse", "board": "http://127.0.0.1/admin"},
        {"kind": "greenhouse", "board": "file:///etc/passwd"},
        {"kind": "greenhouse", "board": "examplerobotics", "region": "eu"},
        {"kind": "lever", "board": "https://jobs.lever.co/x", "region": "eu"},
        {"kind": "lever", "board": "not a slug"},
        {"kind": "community_feed", "board": "anything"},
        {"kind": "greenhouse", "board": ""},
        {"kind": "greenhouse", "board": "examplerobotics", "url": "https://x.example"},
    ],
)
def test_unsafe_or_invalid_sources_are_rejected(client: TestClient, body: dict[str, Any]) -> None:
    response = client.post("/api/sources", json={"display_name": "Example", **body})

    assert response.status_code == 422, response.text
    assert len(client.get("/api/sources").json()) == 1


def test_duplicate_sources_are_rejected(client: TestClient) -> None:
    add_greenhouse(client)

    response = client.post(
        "/api/sources",
        json={
            "kind": "greenhouse",
            "display_name": "Again",
            "board": f"https://boards.greenhouse.io/{GREENHOUSE_BOARD}",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Example Robotics is already configured."}


def test_sources_can_be_renamed_and_disabled_but_not_repointed(client: TestClient) -> None:
    source = builtin(client)

    response = client.put(
        f"/api/sources/{source['id']}", json={"display_name": "Renamed Feed", "enabled": False}
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["identifier"] == BUILTIN_IDENTIFIER

    repoint = client.put(
        f"/api/sources/{source['id']}",
        json={"display_name": "x", "enabled": True, "identifier": "elsewhere"},
    )
    assert repoint.status_code == 422
    assert client.post(f"/api/sources/{source['id']}/sync").status_code == 409  # disabled


def test_unknown_source_is_404(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/api/sources/{missing}/sync").status_code == 404
    assert client.get(f"/api/sources/{missing}/runs").status_code == 404


# --- Sync through the API ------------------------------------------------------------------------


def test_sync_reports_counts_and_history(client: TestClient, web: FakeSource) -> None:
    web.json(FEED_URL, feed(feed_job("a"), feed_job("b", title=None)))
    source = builtin(client)

    run = sync(client, source["id"])

    assert run["status"] == "partial"
    assert (run["fetched_count"], run["created_count"], run["invalid_count"]) == (2, 1, 1)
    assert run["errors"] == [
        {
            "external_id": "b",
            "stage": "normalize",
            "code": "invalid_item",
            "message": "title: Input should be a valid string",
        }
    ]
    assert "jobs" not in run  # never the payload
    assert builtin(client)["latest_run"]["id"] == run["id"]
    [listed] = client.get(f"/api/sources/{source['id']}/runs").json()
    assert listed["id"] == run["id"]


def test_sync_all_runs_every_enabled_source(client: TestClient, web: FakeSource) -> None:
    add_greenhouse(client)
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1)))  # the feed gets a 404

    response = client.post("/api/sources/sync")

    assert response.status_code == 200
    assert sorted(r["status"] for r in response.json()) == ["failed", "success"]
    failed = next(r for r in response.json() if r["status"] == "failed")
    assert failed["error_summary"] == "The source board wasn't found."


def test_a_sync_already_running_is_409(client: TestClient, db: Session, web: FakeSource) -> None:
    from datetime import UTC, datetime

    from app.enums import IngestionRunStatus

    source = db.scalars(select(IngestionSource)).one()
    db.add(
        IngestionRun(source=source, status=IngestionRunStatus.RUNNING, started_at=datetime.now(UTC))
    )
    db.commit()

    assert client.post(f"/api/sources/{source.id}/sync").status_code == 409


# --- Discovery list -----------------------------------------------------------------------------


def test_list_is_paginated_and_freshest_first(client: TestClient, web: FakeSource) -> None:
    jobs = [feed_job(f"job-{n}", posted_at=f"2040-09-{n + 1:02d}T00:00:00Z") for n in range(7)]
    web.json(FEED_URL, feed(*jobs, feed_job("undated", posted_at=None)))
    sync(client, builtin(client)["id"])

    first = page(client, limit=3)
    last = page(client, limit=3, offset=6)

    assert (first["total"], first["limit"], first["offset"]) == (8, 3, 0)
    assert [i["posted_at"][:10] for i in first["items"]] == [
        "2040-09-07",
        "2040-09-06",
        "2040-09-05",
    ]
    assert len(last["items"]) == 2
    assert last["items"][-1]["posted_at"] is None  # unknown dates last
    assert client.get("/api/opportunities", params={"limit": 101}).status_code == 422
    assert client.get("/api/opportunities", params={"offset": -1}).status_code == 422


def test_filters(client: TestClient, web: FakeSource) -> None:
    put_profile(client)
    manual = create(client, title="Manual Synthetic Fellowship", remote_mode="remote")
    gh = add_greenhouse(client)
    web.json(
        FEED_URL,
        feed(
            feed_job("a", title="Synthetic Quantum Intern", company="Example Quantum", remote=True),
            feed_job("b", title="Synthetic 100% Intern", company="Example_Labs"),
        ),
    )
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1), greenhouse_job(2)))
    feed_id = builtin(client)["id"]
    sync(client, feed_id)
    sync(client, gh["id"])
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1)))  # job 2 closes
    sync(client, gh["id"])
    closed_id = page(client, availability="closed")["items"][0]["id"]
    client.put(f"/api/opportunities/{closed_id}/application", json={"status": "applied"})

    def titles(**params: Any) -> set[str]:
        return {i["title"] for i in page(client, **params)["items"]}

    assert page(client)["total"] == 4  # open: 3 imported + the manual one
    assert page(client, availability="all")["total"] == 5
    assert titles(availability="closed") == {"Synthetic Robotics Intern"}
    assert titles(q="quantum") == {"Synthetic Quantum Intern"}
    assert titles(q="example robotics") == {"Synthetic Robotics Intern"}
    assert titles(q="100%") == {"Synthetic 100% Intern"}  # wildcards are literal
    assert titles(q="example_labs") == {"Synthetic 100% Intern"}
    assert titles(q="nothing-matches") == set()
    assert titles(source="manual") == {"Manual Synthetic Fellowship"}
    assert len(titles(source=feed_id)) == 2
    assert titles(remote_mode="remote") == {
        "Manual Synthetic Fellowship",
        "Synthetic Quantum Intern",
    }
    assert page(client, eligibility="needs_verification")["total"] == 4
    assert page(client, eligibility="eligible")["total"] == 0
    assert page(client, application_status="tracked", availability="all")["total"] == 1
    assert page(client, application_status="applied")["total"] == 0  # closed, hidden by default
    assert page(client, application_status="untracked")["total"] == 4

    item = next(i for i in page(client)["items"] if i["title"] == "Synthetic Quantum Intern")
    assert (item["origin"], item["availability"]) == ("imported", "open")
    assert item["source_names"] == ["Tech Internship Discovery Feed"]
    manual_item = next(i for i in page(client)["items"] if i["id"] == manual["id"])
    assert (manual_item["origin"], manual_item["availability"]) == ("manual", "manual")

    for bad in ({"availability": "maybe"}, {"source": "feed"}, {"eligibility": "x"}):
        assert client.get("/api/opportunities", params=bad).status_code == 422


# --- Detail provenance and manual review --------------------------------------------------------


def test_imported_detail_shows_provenance_and_can_be_reviewed(
    client: TestClient, db: Session, web: FakeSource
) -> None:
    put_profile(client)
    web.json(FEED_URL, feed(feed_job("a", title="Synthetic Engineering Intern")))
    feed_source = builtin(client)
    sync(client, feed_source["id"])
    [item] = page(client)["items"]

    detail = client.get(f"/api/opportunities/{item['id']}").json()
    assert detail["requirements_assessment_status"] == "unassessed"
    assert detail["latest_evaluation"]["eligibility_status"] == "needs_verification"
    assert detail["manually_curated_at"] is None
    assert (detail["origin"], detail["availability"]) == ("imported", "open")
    [record] = detail["sources"]
    assert record["source_name"] == "Tech Internship Discovery Feed"
    assert record["automated"] is True and record["is_active"] is True
    assert record["source_url"].startswith("https://careers.example.com/")
    assert "raw_payload" not in record

    # The owner reviews the requirements (reusing the regular editor/API).
    reviewed = client.put(
        f"/api/opportunities/{item['id']}",
        json=opportunity(
            title="Synthetic Engineering Intern",
            organization="Example Robotics",
            opportunity_type="internship",
            requirements_assessment_status="complete",
            requirements=[AGE_16, INCOMING_UNDERGRAD],
        ),
    ).json()
    assert reviewed["latest_evaluation"]["eligibility_status"] == "eligible"
    assert reviewed["manually_curated_at"] is not None
    evaluations = db.scalar(select(func.count()).select_from(OpportunityEvaluation))

    # A later sync with upstream changes keeps the review.
    web.json(FEED_URL, feed(feed_job("a", title="Upstream Renamed")))
    assert sync(client, feed_source["id"])["updated_count"] == 1
    after = client.get(f"/api/opportunities/{item['id']}").json()
    assert after["title"] == "Synthetic Engineering Intern"
    assert after["requirements_assessment_status"] == "complete"
    assert len(after["requirements"]) == 2
    assert after["latest_evaluation"]["eligibility_status"] == "eligible"
    assert db.scalar(select(func.count()).select_from(OpportunityEvaluation)) == evaluations

    # The posting disappears: closed, not deleted, and tracking survives.
    client.put(f"/api/opportunities/{item['id']}/application", json={"status": "applied"})
    web.json(FEED_URL, feed())
    assert sync(client, feed_source["id"])["closed_count"] == 1
    closed = client.get(f"/api/opportunities/{item['id']}").json()
    assert closed["availability"] == "closed"
    assert closed["sources"][0]["is_active"] is False
    assert closed["sources"][0]["closed_at"] is not None
    assert closed["application"]["status"] == "applied"


def test_manual_title_edit_does_not_append_an_evaluation(client: TestClient, db: Session) -> None:
    put_profile(client)
    created = create(client, requirements=[AGE_16])

    client.put(
        f"/api/opportunities/{created['id']}",
        json=opportunity(title="Renamed", requirements=[AGE_16]),
    )
    assert db.scalar(select(func.count()).select_from(OpportunityEvaluation)) == 1

    client.put(
        f"/api/opportunities/{created['id']}",
        json=opportunity(title="Renamed", requirements=[AGE_16], start_date="2041-07-01"),
    )
    assert db.scalar(select(func.count()).select_from(OpportunityEvaluation)) == 2
    # The explicit evaluate action still always appends.
    client.post(f"/api/opportunities/{created['id']}/evaluate")
    assert db.scalar(select(func.count()).select_from(OpportunityEvaluation)) == 3


def test_manual_opportunity_is_curated_from_creation(client: TestClient) -> None:
    created = create(client)
    assert created["manually_curated_at"] is not None
    assert (created["origin"], created["availability"]) == ("manual", "manual")
    assert [s["source_name"] for s in created["sources"]] == ["Manual entry"]
