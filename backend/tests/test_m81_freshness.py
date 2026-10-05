"""Milestone 8.1 (ADR-015): listing freshness, discovered filters, independent coverage, and the
Direct Source Catalog, over real rows. Synthetic companies only."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.enums import (
    IngestionRunStatus,
    IngestionSourceKind,
    OpportunitySourceType,
    OpportunityType,
    SourceScope,
)
from app.models import IngestionRun, IngestionSource, Opportunity, OpportunitySourceRecord
from app.services import direct_catalog, source_discovery

pytestmark = [pytest.mark.postgres, pytest.mark.registry]

NOW = datetime.now(UTC)
TODAY = NOW.date()


def _builtin(db: Session, kind: IngestionSourceKind) -> IngestionSource:
    return db.scalars(select(IngestionSource).where(IngestionSource.kind == kind)).one()


def _ran(
    db: Session, source: IngestionSource, status: IngestionRunStatus, hours_ago: float = 1
) -> IngestionSource:
    at = NOW - timedelta(hours=hours_ago)
    db.add(IngestionRun(source_id=source.id, status=status, started_at=at, finished_at=at))
    if status in (IngestionRunStatus.SUCCESS, IngestionRunStatus.NO_CHANGE):
        source.last_success_at = at
    db.flush()
    return source


def _ats(db: Session, identifier: str) -> IngestionSource:
    source = IngestionSource(
        kind=IngestionSourceKind.GREENHOUSE,
        identifier=identifier,
        display_name=identifier.title(),
        scope=SourceScope.INTERNSHIPS_ONLY,
    )
    db.add(source)
    db.flush()
    return source


def _opportunity(
    db: Session, title: str, *, first_seen_days_ago: float = 0, verify_by: date | None = None
) -> Opportunity:
    seen = NOW - timedelta(days=first_seen_days_ago)
    opp = Opportunity(
        title=title,
        organization="Example Robotics",
        opportunity_type=OpportunityType.INTERNSHIP,
        first_seen_at=seen,
        last_seen_at=seen,
        verify_by=verify_by,
    )
    db.add(opp)
    db.flush()
    return opp


def _record(
    db: Session,
    opp: Opportunity,
    source: IngestionSource | None,
    source_type: OpportunitySourceType,
    *,
    active: bool = True,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        OpportunitySourceRecord(
            opportunity_id=opp.id,
            source_name=source.key if source else f"manual-{opp.id}",
            source_type=source_type,
            external_id=f"{opp.title}-{source_type.value}",
            raw_payload=payload or {},
            fetched_at=NOW,
            ingestion_source_id=source.id if source else None,
            is_active=active,
            closed_at=None if active else NOW,
        )
    )
    db.flush()


@pytest.fixture
def catalog_world(db: Session) -> dict[str, Opportunity]:
    """A: healthy ATS + feed; B: feed only; C: partial ATS only; D: manual; E: registry past its
    verify-by; F: registry current; G: closed; H: feed only, found 10 days ago."""
    feed = _ran(db, _builtin(db, IngestionSourceKind.COMMUNITY_FEED), IngestionRunStatus.NO_CHANGE)
    registry = _ran(
        db, _builtin(db, IngestionSourceKind.CURATED_REGISTRY), IngestionRunStatus.SUCCESS
    )
    healthy = _ran(db, _ats(db, "m81healthy"), IngestionRunStatus.SUCCESS, 3)
    partial = _ran(db, _ats(db, "m81partial"), IngestionRunStatus.SUCCESS, 30)
    _ran(db, partial, IngestionRunStatus.PARTIAL, 1)

    world = {key: _opportunity(db, f"M81 {key} Intern") for key in "ABCDG"}
    world["E"] = _opportunity(db, "M81 E Intern", verify_by=TODAY - timedelta(days=1))
    world["F"] = _opportunity(db, "M81 F Intern", verify_by=TODAY + timedelta(days=9))
    world["H"] = _opportunity(db, "M81 H Intern", first_seen_days_ago=10)
    ats, feed_t, reg = (
        OpportunitySourceType.ATS,
        OpportunitySourceType.PUBLIC_FEED,
        OpportunitySourceType.CURATED_REGISTRY,
    )
    _record(db, world["A"], healthy, ats)
    _record(db, world["A"], feed, feed_t)
    _record(db, world["B"], feed, feed_t)
    _record(db, world["C"], partial, ats)
    _record(db, world["D"], None, OpportunitySourceType.MANUAL)
    _record(db, world["E"], registry, reg, payload={"last_verified": "2026-09-30"})
    _record(db, world["F"], registry, reg, payload={"last_verified": "2026-10-04"})
    _record(db, world["G"], healthy, ats, active=False)
    _record(db, world["H"], feed, feed_t)
    db.commit()  # a savepoint release: the test's outer transaction still rolls everything back
    return world


def _page(client: TestClient, **params: Any) -> dict[str, dict[str, Any]]:
    response = client.get(
        "/api/opportunities", params={"q": "M81", "limit": 100, "availability": "all", **params}
    )
    assert response.status_code == 200, response.text
    return {item["title"].split()[1]: item for item in response.json()["items"]}


def test_list_freshness_states(client: TestClient, catalog_world: dict[str, Opportunity]) -> None:
    items = _page(client)
    assert {k: v["freshness"] for k, v in items.items()} == {
        "A": "direct_verified",
        "B": "feed_current",
        "C": "source_warning",
        "D": "manual",
        "E": "program_recheck",
        "F": "program_listed",
        "G": "closed",
        "H": "feed_current",
    }
    assert items["A"]["freshness_checked_at"] is not None
    assert items["F"]["program_last_verified"] == "2026-10-04"
    assert items["B"]["program_last_verified"] is None


def test_freshness_filters(client: TestClient, catalog_world: dict[str, Opportunity]) -> None:
    assert set(_page(client, freshness="direct_verified")) == {"A"}
    assert set(_page(client, freshness="needs_review")) == {"C", "E"}
    assert client.get("/api/opportunities", params={"freshness": "bogus"}).status_code == 422


def test_discovered_filter_and_sort(
    client: TestClient, catalog_world: dict[str, Opportunity]
) -> None:
    week = _page(client, discovered_within=7)
    assert "H" not in week and "A" in week
    assert set(_page(client, discovered_within="1")) == set(week)
    assert client.get("/api/opportunities", params={"discovered_within": 3}).status_code == 422
    response = client.get(
        "/api/opportunities", params={"q": "M81", "availability": "all", "sort": "discovered"}
    )
    titles = [item["title"] for item in response.json()["items"]]
    assert titles[-1] == "M81 H Intern"


def test_detail_freshness_and_source_health(
    client: TestClient, catalog_world: dict[str, Opportunity]
) -> None:
    detail = client.get(f"/api/opportunities/{catalog_world['A'].id}").json()
    assert detail["freshness"] == "direct_verified"
    health = {s["source_type"]: s["source_health"] for s in detail["sources"]}
    assert health == {"ats": "healthy", "public_feed": "healthy"}
    assert all(s["source_last_success_at"] for s in detail["sources"])
    response = client.get(f"/api/opportunities/{catalog_world['D'].id}")
    assert response.status_code == 200, response.text
    manual = response.json()
    assert manual["freshness"] == "manual"
    assert manual["sources"][0]["source_health"] is None


def test_list_statement_count_is_constant(
    client: TestClient, db: Session, catalog_world: dict[str, Opportunity]
) -> None:
    client.get("/api/opportunities", params={"q": "M81", "limit": 1})  # warm the session
    counts: list[int] = []
    for limit in (2, 8):
        statements: list[str] = []

        def count(*args: Any, statements: list[str] = statements) -> None:
            statements.append(args[2])

        event.listen(db.get_bind(), "before_cursor_execute", count)
        try:
            client.get("/api/opportunities", params={"q": "M81", "limit": limit})
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", count)
        counts.append(len(statements))
    assert counts[0] == counts[1]


def test_independent_coverage(db: Session, catalog_world: dict[str, Opportunity]) -> None:
    coverage = source_discovery.discover(db).coverage
    # Open: A B C D E F H (G closed). Independent: A, C (ATS), D (manual), E, F (registry).
    # Only the M81 rows exist in this transaction besides any seeded by other fixtures, so
    # compare differences against the known world.
    assert coverage.independent - coverage.manual_only >= 4
    assert coverage.feed_only >= 2
    assert coverage.direct_fresh >= 1
    assert coverage.curated_registry >= 2
    assert coverage.independent + coverage.feed_only == coverage.active_opportunities
    assert coverage.independent_percent == round(
        coverage.independent / coverage.active_opportunities * 100, 1
    )


# --- Direct Source Catalog -----------------------------------------------------------------------


def test_catalog_file_is_valid() -> None:
    entries = direct_catalog.load_catalog()
    assert entries
    assert all(e.verified_at <= date.today() for e in entries)


def _write(tmp_path: Path, sources: list[dict[str, Any]]) -> Path:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"schema_version": 1, "sources": sources}), encoding="utf-8")
    return path


ENTRY = {
    "organization": "Example Robotics",
    "kind": "greenhouse",
    "identifier": "examplerobotics",
    "region": None,
    "careers_url": "https://example.com/careers",
    "evidence": "synthetic",
    "verified_at": "2026-10-05",
    "tags": ["robotics"],
}


@pytest.mark.parametrize(
    "bad",
    [
        {"identifier": "ExampleRobotics"},  # not canonical
        {"identifier": "../evil"},
        {"kind": "community_feed"},
        {"careers_url": "http://example.com"},
        {"tags": ["not-a-tag"]},
        {"extra": "field"},
        {"kind": "lever", "region": None},
    ],
)
def test_catalog_rejects_invalid_entries(tmp_path: Path, bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        direct_catalog.load_catalog(_write(tmp_path, [{**ENTRY, **bad}]))


def test_catalog_rejects_duplicates(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        direct_catalog.load_catalog(_write(tmp_path, [ENTRY, {**ENTRY, "organization": "Dup"}]))


@pytest.fixture
def fake_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    entries = direct_catalog.load_catalog(
        _write(tmp_path, [ENTRY, {**ENTRY, "identifier": "exampletwo", "organization": "Two"}])
    )
    monkeypatch.setattr(direct_catalog, "catalog", lambda: entries)


def test_catalog_api(client: TestClient, db: Session, fake_catalog: None) -> None:
    body = client.get("/api/sources/catalog").json()
    assert [e["key"] for e in body["entries"]] == [
        "greenhouse:examplerobotics",
        "greenhouse:exampletwo",
    ]
    assert not any(e["already_configured"] for e in body["entries"])

    selection = {"kind": "greenhouse", "identifier": "examplerobotics", "region": None}
    response = client.post("/api/sources/catalog/add", json={"sources": [selection]})
    assert response.status_code == 201
    created = response.json()["created"]
    assert [(c["display_name"], c["scope"]) for c in created] == [
        ("Example Robotics", "internships_only")
    ]
    assert db.scalars(
        select(IngestionSource).where(IngestionSource.identifier == "examplerobotics")
    ).one()
    # Never synced.
    assert not db.scalars(
        select(IngestionRun).where(IngestionRun.source_id == created[0]["id"])
    ).all()

    again = client.post("/api/sources/catalog/add", json={"sources": [selection]})
    assert again.status_code == 200
    assert again.json()["skipped"] == [
        {"key": "greenhouse:examplerobotics", "reason": "already_configured"}
    ]
    assert client.get("/api/sources/catalog").json()["entries"][0]["already_configured"]


def test_catalog_add_refuses_unknown_and_duplicates(client: TestClient, fake_catalog: None) -> None:
    unknown = {"kind": "greenhouse", "identifier": "notincatalog", "region": None}
    known = {"kind": "greenhouse", "identifier": "exampletwo", "region": None}
    response = client.post("/api/sources/catalog/add", json={"sources": [known, unknown]})
    assert response.status_code == 422
    # All-or-nothing: the known one wasn't created either.
    assert not client.get("/api/sources/catalog").json()["entries"][1]["already_configured"]
    duplicate = client.post("/api/sources/catalog/add", json={"sources": [known, known]})
    assert duplicate.status_code == 422
    extra = client.post(
        "/api/sources/catalog/add", json={"sources": [{**known, "display_name": "x"}]}
    )
    assert extra.status_code == 422


def test_catalog_requires_auth(anon_client: TestClient) -> None:
    assert anon_client.get("/api/sources/catalog").status_code == 401


def test_catalog_add_requires_csrf(client: TestClient) -> None:
    client.headers.pop("X-CSRF-Token")
    response = client.post("/api/sources/catalog/add", json={"sources": []})
    assert response.status_code == 403
