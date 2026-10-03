"""Source coverage and discovery (ADR-013 §2, §3): service-level tests of `discover` and
`add_from_discovery`, plus API route shape, auth/CSRF, and query-count/zero-network guarantees.
Synthetic companies and boards only."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.enums import (
    IngestionSourceKind,
    OpportunitySourceType,
    OpportunityType,
    SourceRegion,
    SourceScope,
)
from app.models import IngestionRun, IngestionSource, Opportunity, OpportunitySourceRecord
from app.schemas.source_discovery import MAX_DISCOVERY_ADD, DiscoveryAddRequest, DiscoverySelection
from app.services import source_discovery

pytestmark = pytest.mark.postgres

GH_BOARD = "examplerobotics"
LEVER_SITE = "exampleinstitute"
LEVER_UUID = "0a1b2c3d-0000-4000-8000-000000000001"
ASHBY_BOARD = "example-board"
ASHBY_UUID = "1b2c3d4e-0000-4000-8000-000000000001"


# --- Seeding helpers (direct ORM inserts; ADR-013 §2 is read-only/derived, no pipeline needed) --


def builtin_source(db: Session) -> IngestionSource:
    return db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.COMMUNITY_FEED)
    ).one()


_counter = 0


def _next_id() -> str:
    global _counter
    _counter += 1
    return f"synthetic-{_counter}"


def make_opportunity(
    db: Session,
    *,
    title: str = "Synthetic Intern",
    organization: str = "Example Robotics",
    description: str | None = None,
) -> Opportunity:
    opp = Opportunity(
        title=title,
        organization=organization,
        opportunity_type=OpportunityType.INTERNSHIP,
        description=description,
    )
    db.add(opp)
    db.flush()
    return opp


def make_record(
    db: Session,
    opp: Opportunity,
    *,
    source: IngestionSource | None,
    external_id: str | None,
    source_url: str | None = None,
    source_type: OpportunitySourceType = OpportunitySourceType.PUBLIC_FEED,
    company: str | None = None,
    is_active: bool = True,
) -> OpportunitySourceRecord:
    record = OpportunitySourceRecord(
        opportunity_id=opp.id,
        source_name=source.key if source else f"manual-{_next_id()}",
        source_type=source_type,
        external_id=external_id,
        source_url=source_url,
        raw_payload={"company": company} if company is not None else {},
        fetched_at=datetime.now(UTC),
        ingestion_source_id=source.id if source else None,
        is_active=is_active,
        closed_at=None if is_active else datetime.now(UTC),
    )
    db.add(record)
    db.flush()
    return record


def gh_fields(board: str = GH_BOARD, job: str | None = None) -> tuple[str, str]:
    job = job or _next_id().split("-")[-1].rjust(5, "0")
    return f"greenhouse:{board}:{job}", f"https://job-boards.greenhouse.io/{board}/jobs/{job}"


def lever_fields(
    site: str = LEVER_SITE, posting: str = LEVER_UUID, region: str = "global"
) -> tuple[str, str]:
    host = "jobs.lever.co" if region == "global" else "jobs.eu.lever.co"
    return f"lever:{site}:{posting}", f"https://{host}/{site}/{posting}"


def ashby_fields(board: str = ASHBY_BOARD, posting: str = ASHBY_UUID) -> tuple[str, str]:
    return f"ashby:{board}:{posting}", f"https://jobs.ashbyhq.com/{board}/{posting}"


def ats_source(
    db: Session, kind: IngestionSourceKind, identifier: str, region: SourceRegion | None = None
) -> IngestionSource:
    source = IngestionSource(
        kind=kind,
        identifier=identifier,
        region=region,
        display_name="Configured Co",
        scope=SourceScope.INTERNSHIPS_ONLY,
    )
    db.add(source)
    db.flush()
    return source


# --- Coverage metrics ----------------------------------------------------------------------------


def test_coverage_metrics(db: Session) -> None:
    feed = builtin_source(db)

    # Feed-only, unsupported provider, no description.
    unsupported = make_opportunity(db, title="Unsupported Intern")
    make_record(db, unsupported, source=feed, external_id="workday:acme:1", company="Acme")

    # Feed-only, enrichable (Greenhouse), with a description.
    enrichable_opp = make_opportunity(db, title="Enrichable Intern", description="Build robots.")
    gh_id, gh_url = gh_fields()
    make_record(
        db,
        enrichable_opp,
        source=feed,
        external_id=gh_id,
        source_url=gh_url,
        company="Example Robotics",
    )

    # ATS-backed (no feed record at all).
    gh_source = ats_source(db, IngestionSourceKind.GREENHOUSE, "otherboard")
    ats_backed = make_opportunity(db, title="ATS Intern")
    make_record(
        db,
        ats_backed,
        source=gh_source,
        external_id="999",
        source_type=OpportunitySourceType.ATS,
    )

    # Manual only (open, but not automated at all).
    manual = make_opportunity(db, title="Manual Intern", description="")
    make_record(db, manual, source=None, external_id=None, source_type=OpportunitySourceType.MANUAL)

    # Closed: the only automated record is inactive -> excluded entirely.
    closed = make_opportunity(db, title="Closed Intern")
    make_record(db, closed, source=feed, external_id="workday:acme:2", is_active=False)

    result = source_discovery.discover(db)
    coverage = result.coverage

    assert coverage.active_opportunities == 4
    assert coverage.with_description == 1
    assert coverage.without_description == 3
    assert coverage.description_coverage_percent == 25.0
    assert coverage.ats_backed == 1
    assert coverage.feed_only == 2
    assert coverage.enrichable == 1
    assert coverage.unsupported == 1


def test_empty_catalog_has_no_coverage_percent(db: Session) -> None:
    result = source_discovery.discover(db)
    assert result.coverage.active_opportunities == 0
    assert result.coverage.description_coverage_percent is None


# --- Suggestions: Greenhouse / Lever (global + EU) / Ashby ---------------------------------------


def test_greenhouse_lever_ashby_suggestions(db: Session) -> None:
    feed = builtin_source(db)

    gh_id, gh_url = gh_fields()
    gh_opp = make_opportunity(db, title="Robotics Intern")
    make_record(
        db, gh_opp, source=feed, external_id=gh_id, source_url=gh_url, company="Example Robotics"
    )

    lever_id, lever_url = lever_fields(region="global")
    lever_opp = make_opportunity(db, title="Research Intern")
    make_record(
        db,
        lever_opp,
        source=feed,
        external_id=lever_id,
        source_url=lever_url,
        company="Example Institute",
    )

    lever_eu_id, lever_eu_url = lever_fields(
        posting="0a1b2c3d-0000-4000-8000-000000000002", region="eu"
    )
    lever_eu_opp = make_opportunity(db, title="EU Research Intern")
    make_record(
        db,
        lever_eu_opp,
        source=feed,
        external_id=lever_eu_id,
        source_url=lever_eu_url,
        company="Example Institute",
    )

    ashby_id, ashby_url = ashby_fields()
    ashby_opp = make_opportunity(db, title="Data Science Intern")
    make_record(
        db,
        ashby_opp,
        source=feed,
        external_id=ashby_id,
        source_url=ashby_url,
        company="Example Board Inc.",
    )

    result = source_discovery.discover(db)
    by_key = {s.key: s for s in result.suggestions}

    assert by_key["greenhouse:examplerobotics"].matching_opportunities == 1
    assert by_key["greenhouse:examplerobotics"].suggested_display_name == "Example Robotics"
    assert by_key["lever:global:exampleinstitute"].region == SourceRegion.GLOBAL
    assert by_key["lever:eu:exampleinstitute"].region == SourceRegion.EU
    assert by_key["ashby:example-board"].suggested_display_name == "Example Board Inc."
    for suggestion in by_key.values():
        assert suggestion.already_configured is False
        assert suggestion.display_name_ambiguous is False


def test_ambiguous_company_label_picks_most_common_then_alphabetical(db: Session) -> None:
    feed = builtin_source(db)
    gh_id, gh_url = gh_fields()

    opp_a = make_opportunity(db, title="Intern A")
    make_record(
        db, opp_a, source=feed, external_id=gh_id, source_url=gh_url, company="Zeta Robotics"
    )
    opp_b = make_opportunity(db, title="Intern B")
    gh_id_b, gh_url_b = gh_fields()
    make_record(
        db, opp_b, source=feed, external_id=gh_id_b, source_url=gh_url_b, company="Alpha Robotics"
    )

    result = source_discovery.discover(db)
    [suggestion] = [s for s in result.suggestions if s.key == "greenhouse:examplerobotics"]

    assert suggestion.matching_opportunities == 2
    assert suggestion.display_name_ambiguous is True
    assert suggestion.suggested_display_name == "Alpha Robotics"  # tie -> alphabetical
    assert suggestion.sample_titles == ["Intern A", "Intern B"]


def test_already_configured_suggestion_is_flagged(db: Session) -> None:
    feed = builtin_source(db)
    ats_source(db, IngestionSourceKind.GREENHOUSE, GH_BOARD)
    gh_id, gh_url = gh_fields()
    opp = make_opportunity(db)
    make_record(
        db, opp, source=feed, external_id=gh_id, source_url=gh_url, company="Example Robotics"
    )

    result = source_discovery.discover(db)
    [suggestion] = [s for s in result.suggestions if s.key == "greenhouse:examplerobotics"]

    assert suggestion.already_configured is True


def test_closed_feed_record_is_excluded(db: Session) -> None:
    feed = builtin_source(db)
    gh_id, gh_url = gh_fields()
    opp = make_opportunity(db)
    make_record(db, opp, source=feed, external_id=gh_id, source_url=gh_url, is_active=False)

    result = source_discovery.discover(db)

    assert result.suggestions == []
    assert result.coverage.active_opportunities == 0


def test_eu_greenhouse_host_is_unsupported_not_a_suggestion(db: Session) -> None:
    feed = builtin_source(db)
    gh_id, _ = gh_fields()
    eu_url = f"https://job-boards.eu.greenhouse.io/{GH_BOARD}/jobs/{gh_id.rsplit(':', 1)[-1]}"
    opp = make_opportunity(db)
    make_record(
        db, opp, source=feed, external_id=gh_id, source_url=eu_url, company="Example Robotics"
    )

    result = source_discovery.discover(db)

    assert result.suggestions == []
    [provider] = [p for p in result.providers if p.provider == "greenhouse"]
    assert provider.opportunities == 1
    assert provider.enrichable == 0
    assert result.coverage.unsupported == 1
    assert result.coverage.enrichable == 0


def test_company_label_never_creates_identity(db: Session) -> None:
    """A spoofed company label never proves a board; it's a display hint only (ADR-013 §2)."""
    feed = builtin_source(db)
    opp = make_opportunity(db)
    # Unsupported provider ID, but a company label that *looks* like a provider key.
    make_record(
        db,
        opp,
        source=feed,
        external_id="workday:acme:1",
        company="greenhouse:examplerobotics",
    )

    result = source_discovery.discover(db)

    assert result.suggestions == []
    assert result.coverage.unsupported == 1


def test_provider_distribution(db: Session) -> None:
    feed = builtin_source(db)
    gh_id, gh_url = gh_fields()
    make_record(
        db, make_opportunity(db), source=feed, external_id=gh_id, source_url=gh_url, company="A"
    )
    make_record(db, make_opportunity(db), source=feed, external_id="workday:acme:1", company="B")
    make_record(db, make_opportunity(db), source=feed, external_id="oracle:acme:1", company="C")
    make_record(db, make_opportunity(db), source=feed, external_id="some-ats:acme:1", company="D")

    result = source_discovery.discover(db)
    by_provider = {p.provider: p for p in result.providers}

    assert by_provider["greenhouse"].supported is True
    assert by_provider["greenhouse"].enrichable == 1
    assert by_provider["workday"].supported is False
    assert by_provider["oracle"].supported is False
    assert by_provider["other"].opportunities == 1  # "some-ats" isn't a known prefix


# --- Query count and zero network calls -----------------------------------------------------


def test_discover_runs_a_small_constant_number_of_queries(db: Session) -> None:
    feed = builtin_source(db)
    for _ in range(15):
        gh_id, gh_url = gh_fields(board=f"board-{_next_id()}")
        make_record(
            db,
            make_opportunity(db),
            source=feed,
            external_id=gh_id,
            source_url=gh_url,
            company="X",
        )

    queries = 0

    def _count(*_args: Any, **_kwargs: Any) -> None:
        nonlocal queries
        queries += 1

    event.listen(db.connection(), "before_cursor_execute", _count)
    try:
        source_discovery.discover(db)
    finally:
        event.remove(db.connection(), "before_cursor_execute", _count)

    assert queries <= 5, f"discover() ran {queries} queries"


def test_discover_makes_zero_network_calls(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("discover() must never touch the network")

    monkeypatch.setattr("app.ingestion.http.fetch_json", _boom)
    feed = builtin_source(db)
    gh_id, gh_url = gh_fields()
    make_record(
        db, make_opportunity(db), source=feed, external_id=gh_id, source_url=gh_url, company="X"
    )

    source_discovery.discover(db)  # must not raise


# --- add_from_discovery ---------------------------------------------------------------------


def _seed_suggestion(db: Session) -> tuple[Opportunity, str, str]:
    feed = builtin_source(db)
    gh_id, gh_url = gh_fields()
    opp = make_opportunity(db)
    make_record(
        db, opp, source=feed, external_id=gh_id, source_url=gh_url, company="Example Robotics"
    )
    return opp, gh_id, gh_url


def test_add_creates_source_with_internships_only_scope_and_suggested_name(db: Session) -> None:
    _seed_suggestion(db)
    request = DiscoveryAddRequest(
        sources=[DiscoverySelection(kind=IngestionSourceKind.GREENHOUSE, identifier=GH_BOARD)]
    )

    result = source_discovery.add_from_discovery(db, request)

    assert len(result.created) == 1
    created = result.created[0]
    assert created.scope == SourceScope.INTERNSHIPS_ONLY
    assert created.display_name == "Example Robotics"
    assert result.skipped == []
    assert db.scalars(select(IngestionRun)).first() is None  # never syncs


def test_add_rejects_more_than_the_max(db: Session) -> None:
    selections = [
        DiscoverySelection(kind=IngestionSourceKind.GREENHOUSE, identifier=f"board-{i}")
        for i in range(MAX_DISCOVERY_ADD + 1)
    ]
    with pytest.raises(ValidationError):
        DiscoveryAddRequest(sources=selections)


def test_add_rejects_unknown_or_forged_suggestion_and_creates_nothing(db: Session) -> None:
    before = set(db.execute(select(IngestionSource.id)).all())
    request = DiscoveryAddRequest(
        sources=[
            DiscoverySelection(kind=IngestionSourceKind.GREENHOUSE, identifier="nonexistent-board")
        ]
    )

    with pytest.raises(ValueError):
        source_discovery.add_from_discovery(db, request)

    after = set(db.execute(select(IngestionSource.id)).all())
    assert after == before


def test_add_rejects_duplicate_selection_in_request(db: Session) -> None:
    _seed_suggestion(db)
    request = DiscoveryAddRequest(
        sources=[
            DiscoverySelection(kind=IngestionSourceKind.GREENHOUSE, identifier=GH_BOARD),
            DiscoverySelection(kind=IngestionSourceKind.GREENHOUSE, identifier=GH_BOARD),
        ]
    )

    with pytest.raises(ValueError):
        source_discovery.add_from_discovery(db, request)


def test_add_skips_already_configured(db: Session) -> None:
    _seed_suggestion(db)
    ats_source(db, IngestionSourceKind.GREENHOUSE, GH_BOARD)
    request = DiscoveryAddRequest(
        sources=[DiscoverySelection(kind=IngestionSourceKind.GREENHOUSE, identifier=GH_BOARD)]
    )

    result = source_discovery.add_from_discovery(db, request)

    assert result.created == []
    assert len(result.skipped) == 1
    assert result.skipped[0].key == "greenhouse:examplerobotics"
    assert result.skipped[0].reason == "already_configured"


def test_add_extra_field_is_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        DiscoverySelection.model_validate(
            {"kind": "greenhouse", "identifier": GH_BOARD, "display_name": "Hijacked"}
        )


def test_add_concurrent_duplicate_conflicts_and_creates_nothing(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_suggestion(db)
    lever_opp = make_opportunity(db, title="Lever Intern")
    feed = builtin_source(db)
    lever_id, lever_url = lever_fields()
    make_record(
        db,
        lever_opp,
        source=feed,
        external_id=lever_id,
        source_url=lever_url,
        company="Example Institute",
    )

    real_discover = source_discovery.discover

    def _stale_discover(session: Session):
        response = real_discover(session)
        for suggestion in response.suggestions:
            suggestion.already_configured = False  # pretend nobody has configured it yet
        return response

    monkeypatch.setattr(source_discovery, "discover", _stale_discover)
    # Someone else configures the Greenhouse board inside this same transaction, simulating a
    # race the stale `discover()` snapshot above didn't see.
    ats_source(db, IngestionSourceKind.GREENHOUSE, GH_BOARD)

    request = DiscoveryAddRequest(
        sources=[
            DiscoverySelection(
                kind=IngestionSourceKind.LEVER, identifier=LEVER_SITE, region=SourceRegion.GLOBAL
            ),
            DiscoverySelection(kind=IngestionSourceKind.GREENHOUSE, identifier=GH_BOARD),
        ]
    )

    with pytest.raises(source_discovery.SourceDiscoveryConflict):
        source_discovery.add_from_discovery(db, request)

    # All-or-nothing: the Lever source wasn't created either.
    remaining = db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.LEVER)
    ).all()
    assert remaining == []


# --- API: routes, auth, CSRF ------------------------------------------------------------------


def test_discovery_route_requires_auth(anon_client: TestClient) -> None:
    assert anon_client.get("/api/sources/discovery").status_code == 401


def test_discovery_add_route_requires_csrf(client: TestClient) -> None:
    client.headers.pop("X-CSRF-Token")

    response = client.post("/api/sources/discovery/add", json={"sources": []})

    assert response.status_code == 403


def test_discovery_route_shape(client: TestClient, db: Session) -> None:
    _seed_suggestion(db)
    db.commit()

    response = client.get("/api/sources/discovery")

    assert response.status_code == 200, response.text
    body = response.json()
    assert "coverage" in body and "providers" in body and "suggestions" in body
    [suggestion] = body["suggestions"]
    assert suggestion["key"] == "greenhouse:examplerobotics"


def test_discovery_add_route_shape_and_status(client: TestClient, db: Session) -> None:
    _seed_suggestion(db)
    db.commit()

    response = client.post(
        "/api/sources/discovery/add",
        json={"sources": [{"kind": "greenhouse", "identifier": GH_BOARD}]},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"][0]["kind"] == "greenhouse"
    assert body["skipped"] == []


def test_discovery_add_route_422_for_unknown_suggestion(client: TestClient) -> None:
    response = client.post(
        "/api/sources/discovery/add",
        json={"sources": [{"kind": "greenhouse", "identifier": "nonexistent"}]},
    )

    assert response.status_code == 422, response.text


def test_discovery_add_route_422_for_too_many(client: TestClient) -> None:
    sources = [
        {"kind": "greenhouse", "identifier": f"board-{i}"} for i in range(MAX_DISCOVERY_ADD + 1)
    ]

    response = client.post("/api/sources/discovery/add", json={"sources": sources})

    assert response.status_code == 422, response.text
