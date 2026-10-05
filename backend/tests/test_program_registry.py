"""The curated program registry through the shared pipeline against PostgreSQL (ADR-014 §5-§8).
Synthetic entries in a temporary file; the bundled data file is never read."""

import copy
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import (
    FactReviewState,
    IngestionRunStatus,
    IngestionSourceKind,
    OpportunitySourceType,
    RequirementsAssessmentStatus,
)
from app.ingestion.adapters import program_registry
from app.ingestion.pipeline import sync_enabled_sources, sync_source
from app.models import IngestionRun, IngestionSource, Opportunity, OpportunityRequirement
from tests.ingestion_fixtures import FEED_URL, FakeSource, feed, feed_job
from tests.test_ingestion import count, counts, record
from tests.test_program_registry_unit import ENTRY

pytestmark = [pytest.mark.postgres, pytest.mark.registry]

Write = Callable[..., None]


def entry(slug: str = "example-summer-research", **changes: Any) -> dict[str, Any]:
    result = copy.deepcopy(ENTRY)
    result["slug"] = slug
    result.update(changes)
    return result


@pytest.fixture
def write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Write:
    """Point the registry at a temporary file and (re)write it."""
    path = tmp_path / "r.json"
    monkeypatch.setattr(program_registry, "REGISTRY_PATH", path)

    def _write(*programs: dict[str, Any], raw: str | None = None) -> None:
        path.write_text(
            raw or json.dumps({"schema_version": 1, "programs": list(programs)}), encoding="utf-8"
        )

    return _write


@pytest.fixture
def source(db: Session) -> IngestionSource:
    return db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.CURATED_REGISTRY)
    ).one()


def sync(db: Session, source: IngestionSource) -> IngestionRun:
    return sync_source(db, source)


def only_opportunity(db: Session) -> Opportunity:
    return db.scalars(select(Opportunity)).one()


# --- Import, idempotency, edits ---------------------------------------------------


def test_the_registry_is_a_seeded_builtin_source(source: IngestionSource) -> None:
    assert (source.identifier, source.enabled, source.builtin) == ("program-registry", True, True)


def test_first_sync_creates_opportunities_with_verified_and_typical_dates(
    db: Session, source: IngestionSource, write: Write
) -> None:
    write(entry())
    run = sync(db, source)

    assert run.status is IngestionRunStatus.SUCCESS
    assert counts(run) == {"fetched": 1, "created": 1}
    opportunity = only_opportunity(db)
    assert opportunity.title == "Example Summer Research Program"
    assert opportunity.organization == "Example Institute"
    assert opportunity.application_url == "https://apply.example.org/summer"
    assert opportunity.application_deadline == date(2027, 2, 15)
    assert (opportunity.start_date, opportunity.end_date) == (date(2027, 6, 20), date(2027, 8, 1))
    assert opportunity.program_cycle == "2027"
    assert (opportunity.typical_open_window, opportunity.typical_close_window) == (
        "January",
        "February",
    )
    assert opportunity.verify_by == date(2027, 1, 1)
    assert "Eligibility (summary): Applicants must be at least 16" in (
        opportunity.description or ""
    )
    rec = record(db, source, "example-summer-research:2027")
    assert rec.source_type is OpportunitySourceType.CURATED_REGISTRY
    assert rec.is_active and rec.opportunity_id == opportunity.id
    assert opportunity.manually_curated_at is None


def test_resync_of_an_unchanged_file_is_a_no_op(
    db: Session, source: IngestionSource, write: Write
) -> None:
    write(entry(), entry("example-fall-research", title="Example Fall Research Program"))
    sync(db, source)
    run = sync(db, source)

    assert counts(run) == {"fetched": 2, "unchanged": 2}
    assert count(db, Opportunity) == 2


def test_an_edited_entry_updates_the_same_opportunity(
    db: Session, source: IngestionSource, write: Write
) -> None:
    write(entry())
    sync(db, source)
    first = only_opportunity(db).id

    write(
        entry(
            title="Example Summer Research Program (Renamed)",
            verified={**ENTRY["verified"], "deadline": "2027-02-22"},
        )
    )
    run = sync(db, source)

    assert counts(run) == {"fetched": 1, "updated": 1}
    opportunity = only_opportunity(db)
    assert opportunity.id == first
    assert opportunity.title == "Example Summer Research Program (Renamed)"
    assert opportunity.application_deadline == date(2027, 2, 22)


def test_a_typical_only_entry_has_no_deadline(
    db: Session, source: IngestionSource, write: Write, client: TestClient
) -> None:
    write(
        entry(
            "example-typical-only",
            title="Example Typical Program",
            verified={},
            typical_close_window="Mid February",
        ),
        entry(),
    )
    sync(db, source)

    typical = db.scalars(
        select(Opportunity).where(Opportunity.title == "Example Typical Program")
    ).one()
    assert typical.application_deadline is None
    assert typical.typical_close_window == "Mid February"

    def titles(**params: Any) -> list[str]:
        response = client.get("/api/opportunities", params={"today": "2027-01-01", **params})
        assert response.status_code == 200, response.text
        return [item["title"] for item in response.json()["items"]]

    assert titles(has_deadline="false") == ["Example Typical Program"]
    assert titles(has_deadline="true") == ["Example Summer Research Program"]
    assert titles(sort="deadline") == ["Example Summer Research Program", "Example Typical Program"]
    assert titles(today="2027-02-01", deadline_within=30) == ["Example Summer Research Program"]


def test_a_new_cycle_is_a_new_opportunity(
    db: Session, source: IngestionSource, write: Write
) -> None:
    write(entry())
    sync(db, source)
    write(entry(), entry(cycle="2028", verified={}))
    run = sync(db, source)

    assert counts(run) == {"fetched": 2, "created": 1, "unchanged": 1}
    assert count(db, Opportunity) == 2


def test_a_removed_entry_is_closed_not_deleted_and_can_return(
    db: Session, source: IngestionSource, write: Write, client: TestClient
) -> None:
    write(entry(), entry("example-fall-research", title="Example Fall Research Program"))
    sync(db, source)
    write(entry())
    run = sync(db, source)

    assert counts(run) == {"fetched": 1, "unchanged": 1, "closed": 1}
    assert count(db, Opportunity) == 2
    gone = record(db, source, "example-fall-research:2027")
    assert not gone.is_active and gone.closed_at is not None
    detail = client.get(f"/api/opportunities/{gone.opportunity_id}").json()
    assert detail["availability"] == "closed"

    write(entry(), entry("example-fall-research", title="Example Fall Research Program"))
    run = sync(db, source)
    assert counts(run) == {"fetched": 2, "unchanged": 2, "reactivated": 1}
    assert count(db, Opportunity) == 2
    assert client.get(f"/api/opportunities/{gone.opportunity_id}").json()["availability"] == "open"


# --- Owner edits win ----------------------------------------------------------


def test_owner_edits_are_never_overwritten_but_the_record_still_updates(
    db: Session, source: IngestionSource, write: Write, client: TestClient
) -> None:
    write(entry())
    sync(db, source)
    opportunity = only_opportunity(db)

    response = client.put(
        f"/api/opportunities/{opportunity.id}",
        json={
            "title": "Owner Title",
            "organization": "Example Institute",
            "opportunity_type": "research",
            "description": "Owner notes.",
            "application_deadline": "2027-03-01",
        },
    )
    assert response.status_code == 200, response.text
    db.expire_all()
    assert only_opportunity(db).manually_curated_at is not None

    write(
        entry(
            title="Upstream Rename",
            description="Upstream description.",
            verified={**ENTRY["verified"], "deadline": "2027-02-22"},
        )
    )
    run = sync(db, source)

    assert counts(run) == {"fetched": 1, "updated": 1}
    db.expire_all()
    kept = only_opportunity(db)
    assert kept.title == "Owner Title"
    assert kept.description == "Owner notes."
    assert kept.application_deadline == date(2027, 3, 1)
    assert record(db, source, "example-summer-research:2027").raw_payload["title"] == (
        "Upstream Rename"
    )


# --- Requirement candidates ----------------------------------------------------------


def test_eligibility_summary_yields_pending_candidates_only(
    db: Session, source: IngestionSource, write: Write
) -> None:
    write(entry(eligibility_summary="Applicants must be at least 16 years old."))
    sync(db, source)

    opportunity = only_opportunity(db)
    assert opportunity.requirement_candidates
    assert {c.review_state for c in opportunity.requirement_candidates} == {FactReviewState.PENDING}
    assert count(db, OpportunityRequirement) == 0
    assert opportunity.requirements_assessment_status is RequirementsAssessmentStatus.UNASSESSED


# --- needs_date_verification ----------------------------------------------------------


def test_needs_date_verification_filter_and_flags(
    db: Session, source: IngestionSource, write: Write, client: TestClient
) -> None:
    write(
        entry("example-due", title="Example Due Program", verify_by="2027-03-01"),
        entry("example-later", title="Example Later Program", verify_by="2027-06-01"),
        entry("example-never", title="Example Never Program", verify_by=None),
    )
    sync(db, source)

    def titles(flag: str) -> list[str]:
        response = client.get(
            "/api/opportunities",
            params={"needs_date_verification": flag, "today": "2027-03-01", "sort": "newest"},
        )
        assert response.status_code == 200, response.text
        return sorted(item["title"] for item in response.json()["items"])

    assert titles("true") == ["Example Due Program"]
    assert titles("false") == ["Example Later Program", "Example Never Program"]

    items = client.get("/api/opportunities").json()["items"]
    by_title = {item["title"]: item for item in items}
    assert by_title["Example Never Program"]["needs_date_verification"] is False
    assert by_title["Example Due Program"]["verify_by"] == "2027-03-01"
    assert by_title["Example Due Program"]["program_cycle"] == "2027"
    detail = client.get(f"/api/opportunities/{by_title['Example Due Program']['id']}").json()
    assert detail["typical_open_window"] == "January"
    assert isinstance(detail["needs_date_verification"], bool)


# --- Identity ----------------------------------------------------------


def test_a_feed_posting_with_the_same_url_never_merges_with_a_program(
    db: Session, source: IngestionSource, write: Write
) -> None:
    feed_source = db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.COMMUNITY_FEED)
    ).one()
    write(entry())
    sync(db, source)

    web = FakeSource()
    web.json(
        FEED_URL, feed(feed_job("workday:example:/job/A", url="https://apply.example.org/summer"))
    )
    run = sync_source(db, feed_source, transport=web.transport())

    assert counts(run) == {"fetched": 1, "created": 1}
    assert count(db, Opportunity) == 2
    program = db.scalars(
        select(Opportunity).where(Opportunity.title == "Example Summer Research Program")
    ).one()
    assert [r.source_type for r in program.source_records] == [
        OpportunitySourceType.CURATED_REGISTRY
    ]


# --- Failures ----------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "{not json",
        json.dumps({"schema_version": 2, "programs": []}),
        json.dumps({"schema_version": 1, "programs": [entry(), entry(title="Same key")]}),
        json.dumps([]),
    ],
)
def test_a_malformed_file_fails_the_run_and_changes_nothing(
    db: Session, source: IngestionSource, write: Write, bad: str
) -> None:
    write(entry())
    sync(db, source)
    before = only_opportunity(db).title

    write(raw=bad)
    run = sync(db, source)

    assert run.status is IngestionRunStatus.FAILED
    assert only_opportunity(db).title == before
    assert record(db, source, "example-summer-research:2027").is_active


def test_a_malformed_entry_is_a_partial_run_and_nothing_closes(
    db: Session, source: IngestionSource, write: Write
) -> None:
    write(entry(), entry("example-fall-research", title="Example Fall Research Program"))
    sync(db, source)

    write(entry(), entry("example-fall-research", cycle="oops"))
    run = sync(db, source)

    assert run.status is IngestionRunStatus.PARTIAL
    assert run.invalid_count == 1 and run.closed_count == 0
    assert record(db, source, "example-fall-research:2027").is_active


# --- Scheduling and the sources API ----------------------------------------------------------


def test_scheduled_sync_includes_the_registry(
    db: Session, source: IngestionSource, write: Write
) -> None:
    write(entry())
    runs = sync_enabled_sources(db, transport=FakeSource().transport())

    by_source = {run.source_id: run for run in runs}
    assert by_source[source.id].status is IngestionRunStatus.SUCCESS
    # The registry is not the feed, so it syncs before it (the feed's fetches 404 here).
    assert runs[0].source_id == source.id
    assert count(db, Opportunity) == 1


def test_the_registry_source_can_be_disabled_but_not_created_or_filtered(
    client: TestClient, source: IngestionSource
) -> None:
    listed = {s["identifier"]: s for s in client.get("/api/sources").json()}
    assert listed["program-registry"]["builtin"] is True
    assert listed["program-registry"]["scope"] == "all"

    created = client.post(
        "/api/sources",
        json={
            "kind": "curated_registry",
            "display_name": "Another registry",
            "board": "program-registry",
        },
    )
    assert created.status_code == 422

    url = f"/api/sources/{source.id}"
    narrowed = client.put(
        url, json={"display_name": "Registry", "enabled": True, "scope": "internships_only"}
    )
    assert narrowed.status_code == 422, narrowed.text
    disabled = client.put(url, json={"display_name": "Registry", "enabled": False})
    assert disabled.status_code == 200, disabled.text
    assert (disabled.json()["enabled"], disabled.json()["scope"]) == (False, "all")
