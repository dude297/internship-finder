"""The community discovery feed is architecturally optional (ADR-013, ADR-015 §5): with it
disabled, or enabled but down, direct sources and the curated registry still discover, evaluate,
score, rank, and track. Synthetic data only; one in-memory transport, no network."""

import json
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import (
    IngestionRunStatus,
    IngestionSourceKind,
    RequirementAppliesAt,
    RequirementsAssessmentStatus,
    RequirementType,
)
from app.ingestion.adapters import program_registry, smartrecruiters
from app.ingestion.adapters.workable import API as WORKABLE_API
from app.ingestion.http import fetch_json
from app.ingestion.pipeline import sync_enabled_sources
from app.models import IngestionRun, Opportunity, OpportunityRequirement
from tests.ingestion_fixtures import (
    ASHBY_URL,
    FEED_URL,
    GREENHOUSE_URL,
    ashby_board,
    ashby_job,
    feed,
    feed_job,
    greenhouse_board,
    greenhouse_job,
)
from tests.test_api_fit import put_match
from tests.test_api_workflow import put_profile
from tests.test_pinpoint_adapter import payload as pinpoint_payload
from tests.test_pinpoint_adapter import posting as pinpoint_posting
from tests.test_program_registry_unit import ENTRY
from tests.test_smartrecruiters_cross_source import COMPANY as SR_COMPANY
from tests.test_smartrecruiters_cross_source import World, sr_item
from tests.test_workable_adapter import job as workable_job

pytestmark = [pytest.mark.postgres, pytest.mark.registry]

FEED_HOST = "zshah101.github.io"
WORKABLE_URL = f"{WORKABLE_API}/example-robotics?details=true"
PINPOINT_URL = "https://example-space.pinpointhq.com/postings.json"
GH_TITLE = "Synthetic Robotics Intern"
PROGRAM_TITLE = "Example Summer Research Program"


class Web:
    """Serves every direct source and the feed (forbidden, ok, or down)."""

    def __init__(self) -> None:
        self.sr = World()
        self.sr.postings[SR_COMPANY] = [sr_item()]
        self.gh = [greenhouse_job(1001), greenhouse_job(1002, title="Synthetic Second Intern")]
        self.feed_mode = "forbidden"  # forbidden: any request fails the test | ok | down
        self.feed_jobs: list[dict[str, Any]] = []
        self.feed_requests = 0
        self.transport = httpx2.MockTransport(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        if request.url.host == FEED_HOST:
            self.feed_requests += 1
            assert self.feed_mode != "forbidden", f"feed requested while disabled: {url}"
            if self.feed_mode == "down":
                return httpx2.Response(500)
            assert url == FEED_URL
            return httpx2.Response(200, json=feed(*self.feed_jobs))
        bodies = {
            GREENHOUSE_URL: greenhouse_board(*self.gh),
            ASHBY_URL: ashby_board(ashby_job()),
            WORKABLE_URL: {"name": "Example Robotics", "jobs": [workable_job()]},
            PINPOINT_URL: pinpoint_payload(pinpoint_posting()),
        }
        if url in bodies:
            return httpx2.Response(200, json=bodies[url])
        return self.sr.transport.handle_request(request)


def _no_sleep(_seconds: float) -> None:
    return None


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.ingestion.http.time.sleep", _no_sleep)
    monkeypatch.setattr(smartrecruiters, "fetch_json", partial(fetch_json, sleep=_no_sleep))


@pytest.fixture
def registry_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"schema_version": 1, "programs": [ENTRY]}), encoding="utf-8")
    monkeypatch.setattr(program_registry, "REGISTRY_PATH", path)


def _setup_direct_sources(client: TestClient) -> None:
    for kind, name, board in [
        ("greenhouse", "Example Robotics", "examplerobotics"),
        ("ashby", "Example Board", "example-board"),
        ("smartrecruiters", "SR Robotics", SR_COMPANY),
        ("workable", "Workable Robotics", "https://apply.workable.com/example-robotics"),
        ("pinpoint", "Example Space", "https://example-space.pinpointhq.com/"),
    ]:
        body = {"kind": kind, "display_name": name, "board": board}
        response = client.post("/api/sources", json=body)
        assert response.status_code == 201, response.text


def _set_feed(client: TestClient, *, enabled: bool) -> None:
    [row] = [s for s in client.get("/api/sources").json() if s["kind"] == "community_feed"]
    body = {"display_name": row["display_name"], "enabled": enabled}
    response = client.put(f"/api/sources/{row['id']}", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is enabled


def _items(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/api/opportunities", params={"limit": 100, "sort": "recommended"})
    assert response.status_code == 200, response.text
    return {i["title"]: i for i in response.json()["items"]}


def _by_kind(runs: list[IngestionRun]) -> dict[IngestionSourceKind, IngestionRun]:
    return {r.source.kind: r for r in runs}


def test_feed_disabled_everything_still_works(
    db: Session, client: TestClient, registry_file: None
) -> None:
    web = Web()
    put_profile(client)
    put_match(client)
    _setup_direct_sources(client)
    _set_feed(client, enabled=False)

    runs = sync_enabled_sources(db, transport=web.transport)
    assert web.feed_requests == 0
    assert {r.source.kind for r in runs} == {
        IngestionSourceKind.GREENHOUSE,
        IngestionSourceKind.ASHBY,
        IngestionSourceKind.SMARTRECRUITERS,
        IngestionSourceKind.WORKABLE,
        IngestionSourceKind.PINPOINT,
        IngestionSourceKind.CURATED_REGISTRY,
    }
    assert all(r.status is IngestionRunStatus.SUCCESS for r in runs), [r.status for r in runs]

    # Discovery from every direct source and the registry: 2 Greenhouse + 4 others + 1 program.
    items = _items(client)
    assert len(items) == 7, sorted(items)
    assert items[PROGRAM_TITLE]["freshness"] in ("program_listed", "program_recheck")
    assert {t: i["freshness"] for t, i in items.items() if t != PROGRAM_TITLE} == {
        t: "direct_verified" for t in items if t != PROGRAM_TITLE
    }

    # Fit exists for everything; a manual requirement drives eligibility.
    assert all(i["fit_score"] is not None for i in items.values())
    gh = db.scalars(select(Opportunity).where(Opportunity.title == GH_TITLE)).one()
    gh.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    gh.requirements = [
        OpportunityRequirement(
            requirement_type=RequirementType.MINIMUM_AGE,
            value={"years": 99},
            applies_at=RequirementAppliesAt.EXPLICIT_DATE,
            reference_date=date(2041, 6, 20),
            extraction_method="manual",
        )
    ]
    db.commit()
    evaluated = client.post(f"/api/opportunities/{gh.id}/evaluate")
    assert evaluated.status_code == 201, evaluated.text
    assert evaluated.json()["eligibility_status"] == "ineligible"
    ranked = list(_items(client))  # sort=recommended: eligibility first, ineligible last
    assert len(ranked) == 7 and ranked[-1] == GH_TITLE

    tracked = client.put(f"/api/opportunities/{gh.id}/application", json={"status": "saved"})
    assert tracked.status_code == 200, tracked.text

    # Coverage is fully independent of the feed; the catalog endpoints work.
    coverage = client.get("/api/sources/discovery").json()["coverage"]
    assert coverage["active_opportunities"] == 7
    assert coverage["independent"] == 7 and coverage["independent_percent"] == 100.0
    assert coverage["feed_only"] == 0
    catalog = client.get("/api/sources/catalog")
    assert catalog.status_code == 200 and "entries" in catalog.json()

    # A second run changes and closes nothing, and still never asks for the feed.
    for run in sync_enabled_sources(db, transport=web.transport):
        assert run.status in (IngestionRunStatus.NO_CHANGE, IngestionRunStatus.SUCCESS)
        assert (run.created_count, run.updated_count, run.closed_count) == (0, 0, 0)
    assert web.feed_requests == 0 and len(_items(client)) == 7

    # Removing one posting from a direct board closes only that posting.
    web.gh = web.gh[:1]
    runs = _by_kind(sync_enabled_sources(db, transport=web.transport))
    assert runs[IngestionSourceKind.GREENHOUSE].closed_count == 1
    assert sum(r.closed_count for r in runs.values()) == 1
    remaining = _items(client)
    assert len(remaining) == 6 and "Synthetic Second Intern" not in remaining


def test_feed_enabled_but_down_direct_sources_unaffected(
    db: Session, client: TestClient, registry_file: None
) -> None:
    web = Web()
    _setup_direct_sources(client)
    web.feed_mode = "ok"
    web.feed_jobs = [feed_job("workday:example:/job/Feed-Only_R9", title="Feed Only Intern")]
    first = _by_kind(sync_enabled_sources(db, transport=web.transport))
    assert first[IngestionSourceKind.COMMUNITY_FEED].status is IngestionRunStatus.SUCCESS
    assert _items(client)["Feed Only Intern"]["freshness"] == "feed_current"

    web.feed_mode = "down"
    runs = _by_kind(sync_enabled_sources(db, transport=web.transport))
    assert runs[IngestionSourceKind.COMMUNITY_FEED].status is IngestionRunStatus.FAILED
    for kind, run in runs.items():
        assert run.closed_count == 0
        if kind is not IngestionSourceKind.COMMUNITY_FEED:
            assert run.status in (IngestionRunStatus.NO_CHANGE, IngestionRunStatus.SUCCESS)

    items = _items(client)
    assert len(items) == 8  # 7 direct/registry + the feed-only posting; none closed
    assert items["Feed Only Intern"]["freshness"] == "source_warning"
    assert items[GH_TITLE]["freshness"] == "direct_verified"
