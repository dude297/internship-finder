"""Source retirement and feed-free bootstrap (ADR-016). Synthetic payloads only."""

import hashlib
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.enums import (
    ApplicationStatus,
    IngestionRunStatus,
    IngestionSourceKind,
    SourceScope,
)
from app.ingestion.adapters.community_feed import BUILTIN_IDENTIFIER
from app.ingestion.pipeline import sync_source
from app.models import (
    Application,
    IngestionRun,
    IngestionSource,
    Opportunity,
    OpportunitySourceRecord,
)
from app.services import direct_catalog, source_bootstrap, source_retirement
from tests.ingestion_fixtures import (
    ASHBY_BOARD,
    ASHBY_URL,
    FEED_URL,
    GREENHOUSE_BOARD,
    GREENHOUSE_URL,
    FakeSource,
    ashby_board,
    ashby_job,
    feed,
    feed_job,
    greenhouse_board,
    greenhouse_job,
)

pytestmark = pytest.mark.postgres

SHARED_URL = "https://careers.example.com/robotics/shared-posting"
FEED_ONLY_TITLE = "Feed Only Synthetic Intern"


@pytest.fixture(autouse=True)
def cli_uses_test_transaction(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "get_engine", db.connection)


@pytest.fixture
def web() -> FakeSource:
    return FakeSource()


def _source(db: Session, kind: IngestionSourceKind, identifier: str, name: str) -> IngestionSource:
    source = IngestionSource(kind=kind, identifier=identifier, display_name=name)
    db.add(source)
    db.commit()
    return source


@pytest.fixture
def feed_source(db: Session) -> IngestionSource:
    return db.scalars(
        select(IngestionSource).where(IngestionSource.identifier == BUILTIN_IDENTIFIER)
    ).one()


@pytest.fixture
def gh_source(db: Session) -> IngestionSource:
    return _source(db, IngestionSourceKind.GREENHOUSE, GREENHOUSE_BOARD, "Example Robotics")


@pytest.fixture
def ashby_source(db: Session) -> IngestionSource:
    return _source(db, IngestionSourceKind.ASHBY, ASHBY_BOARD, "Example Board")


def _world(db: Session, web: FakeSource, feed_source: IngestionSource, gh: IngestionSource) -> None:
    """One posting known to both the feed and Greenhouse (the board owns it), plus one
    feed-only posting."""
    shared_feed = feed_job(
        f"greenhouse:{GREENHOUSE_BOARD}:1001",
        title="Feed Intern",
        url="https://careers.example.com/robotics?gh_jid=1001",
    )
    web.json(FEED_URL, feed(shared_feed, feed_job("workday:x:/job/R2", title=FEED_ONLY_TITLE)))
    sync_source(db, feed_source, transport=web.transport())
    web.json(
        GREENHOUSE_URL,
        greenhouse_board(
            greenhouse_job(
                1001,
                title="Board Intern",
                absolute_url="https://careers.example.com/robotics?gh_jid=1001",
            )
        ),
    )
    sync_source(db, gh, transport=web.transport())


def _digest(db: Session) -> str:
    db.expire_all()
    rows = [
        (r.id, r.is_active, r.closed_at)
        for r in db.scalars(select(OpportunitySourceRecord).order_by(OpportunitySourceRecord.id))
    ]
    rows += [
        (o.id, o.title, o.description, o.last_seen_at)
        for o in db.scalars(select(Opportunity).order_by(Opportunity.id))
    ]
    rows += [
        (s.id, s.enabled, s.etag, s.last_modified)
        for s in db.scalars(select(IngestionSource).order_by(IngestionSource.id))
    ]
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def _opp(db: Session, title: str) -> Opportunity:
    return db.scalars(select(Opportunity).where(Opportunity.title == title)).one()


def _open(db: Session, opportunity: Opportunity) -> bool:
    db.refresh(opportunity)
    return any(r.is_active for r in opportunity.source_records)


def test_dry_run_changes_nothing(
    db: Session, web: FakeSource, feed_source: IngestionSource, gh_source: IngestionSource
) -> None:
    _world(db, web, feed_source, gh_source)
    before = _digest(db)

    result = source_retirement.retire_source(db, feed_source, apply=False)

    assert (result.records_closed, result.opportunities_closed, result.stayed_open) == (2, 1, 1)
    assert result.applied is False and result.source_disabled is True
    assert _digest(db) == before
    assert feed_source.enabled


def test_feed_retirement_closes_feed_only_and_keeps_direct_backed_open(
    db: Session, web: FakeSource, feed_source: IngestionSource, gh_source: IngestionSource
) -> None:
    _world(db, web, feed_source, gh_source)
    shared = _opp(db, "Board Intern")
    feed_only = _opp(db, FEED_ONLY_TITLE)

    result = source_retirement.retire_source(db, feed_source, apply=True)
    db.commit()

    assert (result.records_closed, result.opportunities_closed, result.stayed_open) == (2, 1, 1)
    assert result.fallbacks == 0  # the board already owned the canonical fields
    assert not feed_source.enabled and feed_source.etag is None
    assert _open(db, shared) and shared.title == "Board Intern"
    assert not _open(db, feed_only)
    assert db.get(Opportunity, feed_only.id) is not None  # closed, never deleted
    closed = [r for r in feed_only.source_records if r.closed_at is not None]
    assert len(closed) == 1


def test_board_retirement_falls_back_to_the_feed(
    db: Session, web: FakeSource, feed_source: IngestionSource, gh_source: IngestionSource
) -> None:
    _world(db, web, feed_source, gh_source)
    shared = _opp(db, "Board Intern")

    result = source_retirement.retire_source(db, gh_source, apply=True)
    db.commit()

    assert (result.records_closed, result.fallbacks, result.stayed_open) == (1, 1, 1)
    assert result.opportunities_closed == 0
    assert _open(db, shared) and shared.title == "Feed Intern"  # the normal ADR-013 §5 fallback
    assert not gh_source.enabled


def test_fallback_to_remaining_ats_source(
    db: Session, web: FakeSource, gh_source: IngestionSource, ashby_source: IngestionSource
) -> None:
    web.json(
        GREENHOUSE_URL,
        greenhouse_board(greenhouse_job(1001, title="Greenhouse Intern", absolute_url=SHARED_URL)),
    )
    sync_source(db, gh_source, transport=web.transport())
    web.json(
        ASHBY_URL,
        ashby_board(ashby_job(title="Ashby Intern", jobUrl=SHARED_URL, applyUrl=SHARED_URL)),
    )
    sync_source(db, ashby_source, transport=web.transport())
    opportunity = db.scalars(select(Opportunity)).one()
    assert opportunity.title == "Greenhouse Intern"

    result = source_retirement.retire_source(db, gh_source, apply=True)
    db.commit()

    assert result.fallbacks == 1 and result.stayed_open == 1
    db.refresh(opportunity)
    assert opportunity.title == "Ashby Intern"
    assert _open(db, opportunity)


def test_curated_content_and_application_tracking_are_untouched(
    db: Session, web: FakeSource, feed_source: IngestionSource, gh_source: IngestionSource
) -> None:
    _world(db, web, feed_source, gh_source)
    curated = _opp(db, "Board Intern")
    curated.manually_curated_at = datetime.now(UTC)
    curated.title = "Owner-Curated Title"
    curated.description = "Owner words."
    other = _opp(db, FEED_ONLY_TITLE)
    db.add(Application(opportunity_id=other.id, status=ApplicationStatus.SAVED, notes="mine"))
    db.add(Application(opportunity_id=curated.id, status=ApplicationStatus.APPLIED))
    db.commit()

    result = source_retirement.retire_source(db, gh_source, apply=True)
    source_retirement.retire_source(db, feed_source, apply=True)
    db.commit()

    assert result.curated_preserved == 1 and result.fallbacks == 0
    db.refresh(curated)
    assert (curated.title, curated.description) == ("Owner-Curated Title", "Owner words.")
    apps = {a.opportunity_id: a for a in db.scalars(select(Application))}
    assert apps[other.id].status is ApplicationStatus.SAVED and apps[other.id].notes == "mine"
    assert apps[curated.id].status is ApplicationStatus.APPLIED


def test_second_run_is_a_no_op(
    db: Session, web: FakeSource, feed_source: IngestionSource, gh_source: IngestionSource
) -> None:
    _world(db, web, feed_source, gh_source)
    source_retirement.retire_source(db, feed_source, apply=True)
    db.commit()
    after_first = _digest(db)

    again = source_retirement.retire_source(db, feed_source, apply=True)
    db.commit()

    assert (again.records_closed, again.opportunities_closed, again.fallbacks) == (0, 0, 0)
    assert _digest(db) == after_first


def test_a_running_sync_refuses_retirement_and_changes_nothing(
    db: Session, web: FakeSource, feed_source: IngestionSource, gh_source: IngestionSource
) -> None:
    _world(db, web, feed_source, gh_source)
    db.add(
        IngestionRun(
            source_id=feed_source.id,
            status=IngestionRunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
    )
    db.commit()
    before = _digest(db)

    with pytest.raises(source_retirement.RetireRefused):
        source_retirement.retire_source(db, feed_source, apply=True)
    assert _digest(db) == before and feed_source.enabled


def test_failure_leaves_source_enabled_and_nothing_closed(
    db: Session,
    web: FakeSource,
    feed_source: IngestionSource,
    gh_source: IngestionSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _world(db, web, feed_source, gh_source)
    before = _digest(db)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(source_retirement, "close_records", boom)
    with pytest.raises(RuntimeError):
        source_retirement.retire_source(db, feed_source, apply=True)
    db.rollback()  # what the CLI does

    assert _digest(db) == before and feed_source.enabled


def test_rollback_reenable_and_next_sync_reopens(
    db: Session, web: FakeSource, feed_source: IngestionSource, gh_source: IngestionSource
) -> None:
    _world(db, web, feed_source, gh_source)
    feed_only = _opp(db, FEED_ONLY_TITLE)
    source_retirement.retire_source(db, feed_source, apply=True)
    db.commit()
    assert not _open(db, feed_only)

    feed_source.enabled = True
    db.commit()
    run = sync_source(db, feed_source, transport=web.transport())

    assert run.status is IngestionRunStatus.SUCCESS and run.reactivated_count == 2
    assert _open(db, feed_only)


def test_cli_dry_run_then_apply_prints_counts_only(
    db: Session,
    web: FakeSource,
    feed_source: IngestionSource,
    gh_source: IngestionSource,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _world(db, web, feed_source, gh_source)
    before = _digest(db)
    capsys.readouterr()

    assert cli.main(["retire-source", feed_source.key]) == 0
    out = capsys.readouterr().out
    assert (
        "dry run" in out and "records_closed 2" in out and "stayed_open_via_other_source 1" in out
    )
    assert FEED_ONLY_TITLE not in out and "postgresql" not in out
    assert _digest(db) == before

    assert cli.main(["retire-source", feed_source.key, "--apply"]) == 0
    assert "applied" in capsys.readouterr().out
    db.expire_all()
    assert not feed_source.enabled
    assert cli.main(["retire-source", "nope:missing"]) == 1


def test_registry_source_can_be_retired_but_never_deleted(db: Session) -> None:
    registry = IngestionSource(
        kind=IngestionSourceKind.CURATED_REGISTRY,
        identifier="program-registry",
        display_name="Curated Program Registry",
        scope=SourceScope.ALL,
    )
    db.add(registry)
    db.commit()
    result = source_retirement.retire_source(db, registry, apply=True)
    db.commit()
    assert result.records_closed == 0 and not registry.enabled and registry.builtin


# --- bootstrap ---------------------------------------------------------------------------------


def _entry(i: int, tags: list[str]) -> direct_catalog.CatalogEntry:
    return direct_catalog.CatalogEntry.model_validate(
        {
            "organization": f"Example {i}",
            "kind": "greenhouse",
            "identifier": f"example{i}",
            "careers_url": "https://example.com/careers",
            "evidence": "synthetic",
            "verified_at": date(2040, 1, 1),
            "tags": tags,
        }
    )


def _catalog(monkeypatch: pytest.MonkeyPatch, n: int, tags: list[str]) -> None:
    entries = tuple(_entry(i, tags if i % 2 == 0 else ["ai"]) for i in range(n))
    monkeypatch.setattr(direct_catalog, "catalog", lambda: entries)


def test_bootstrap_adds_by_tag_is_idempotent_and_never_syncs(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _catalog(monkeypatch, 30, ["robotics"])  # 15 robotics, 15 ai

    dry = source_bootstrap.bootstrap_sources(db, tags=["robotics"], dry_run=True)
    assert (dry.selected, dry.added) == (15, 15)
    assert not db.scalars(
        select(IngestionSource).where(IngestionSource.display_name == "Example 0")
    ).all()

    result = source_bootstrap.bootstrap_sources(db, tags=["robotics"])
    again = source_bootstrap.bootstrap_sources(db, tags=["robotics"])
    assert (result.added, again.added, again.already_configured) == (15, 0, 15)
    added = db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.GREENHOUSE)
    ).all()
    assert len(added) == 15 and all(s.enabled and s.last_attempted_at is None for s in added)
    assert db.scalar(select(IngestionRun.id).limit(1)) is None


def test_bootstrap_refuses_beyond_the_cap_and_unknown_tags(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _catalog(monkeypatch, 51, ["ai"])
    with pytest.raises(source_bootstrap.BootstrapRefused, match="cap"):
        source_bootstrap.bootstrap_sources(db)
    with pytest.raises(source_bootstrap.BootstrapRefused, match="unknown tag"):
        source_bootstrap.bootstrap_sources(db, tags=["nonsense"])
    assert (
        db.scalar(select(IngestionSource.id).where(IngestionSource.display_name == "Example 0"))
        is None
    )


def test_bootstrap_creates_missing_registry_and_disables_a_fresh_feed(
    db: Session, monkeypatch: pytest.MonkeyPatch, feed_source: IngestionSource
) -> None:
    _catalog(monkeypatch, 2, ["ai"])  # the db fixture removed the registry row
    result = source_bootstrap.bootstrap_sources(db, disable_feed=True)
    db.commit()
    assert result.registry_created and result.feed_disabled and not feed_source.enabled
    registry = db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.CURATED_REGISTRY)
    ).one()
    assert registry.enabled and registry.scope.value == "all"


def test_bootstrap_refuses_to_disable_a_feed_with_open_postings(
    db: Session, web: FakeSource, feed_source: IngestionSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    web.json(FEED_URL, feed(feed_job()))
    sync_source(db, feed_source, transport=web.transport())
    _catalog(monkeypatch, 2, ["ai"])
    with pytest.raises(source_bootstrap.BootstrapRefused, match="retire-source"):
        source_bootstrap.bootstrap_sources(db, disable_feed=True)


def test_bootstrap_cli(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _catalog(monkeypatch, 4, ["ai"])
    assert cli.main(["bootstrap-sources", "--dry-run"]) == 0
    assert "catalog_selected 4, added 4" in capsys.readouterr().out
    assert cli.main(["bootstrap-sources", "--tags", "nonsense"]) == 1
    assert cli.main(["bootstrap-sources", "--disable-feed"]) == 0
    db.expire_all()
    feed = db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.COMMUNITY_FEED)
    ).one()
    assert not feed.enabled
