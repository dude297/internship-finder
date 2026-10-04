"""Adversarial review of Milestone 7 (ADR-013): provider identity spoofing, source discovery
abuse, and whether a closing/fallback run can ever leave behind a half-applied canonical
rewrite. Synthetic payloads only; see tests/ingestion_fixtures.py.

Read-only review: no app code was changed to produce these results. Tests that PASS document
secure, already-correct behavior. A test wrapped in xfail(strict=True) proves a real finding the
lead should fix (see its docstring and the final report)."""

from __future__ import annotations

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import IngestionRunStatus, IngestionSourceKind
from app.ingestion.adapters.community_feed import BUILTIN_IDENTIFIER, provider_identity
from app.ingestion.pipeline import sync_enabled_sources
from app.models import IngestionSource, Opportunity
from tests.ingestion_fixtures import (
    FEED_URL,
    GREENHOUSE_BOARD,
    GREENHOUSE_URL,
    FakeSource,
    feed,
    feed_job,
    greenhouse_board,
    greenhouse_job,
)
from tests.test_ingestion import record, sync

pytestmark = pytest.mark.postgres


# --- Fixtures (duplicated from test_ingestion.py: pytest doesn't discover fixtures imported
# into another test module by name) --------------------------------------------------------------


@pytest.fixture
def web() -> FakeSource:
    return FakeSource()


@pytest.fixture
def feed_source(db: Session) -> IngestionSource:
    return db.scalars(
        select(IngestionSource).where(IngestionSource.identifier == BUILTIN_IDENTIFIER)
    ).one()


@pytest.fixture
def gh_source(db: Session) -> IngestionSource:
    source = IngestionSource(
        kind=IngestionSourceKind.GREENHOUSE,
        identifier=GREENHOUSE_BOARD,
        display_name="Example Robotics",
    )
    db.add(source)
    db.commit()
    return source


# --- provider_identity: host-matching edge cases (pure function, no DB) -------------------------


def test_backslash_obfuscated_host_is_not_recognized_as_ashby() -> None:
    """A backslash is not a path separator to urlsplit, so
    "https://jobs.ashbyhq.com\\board\\posting" puts the whole thing in the hostname, not the
    authority. `_hosted_path` must fail closed (no identity) rather than matching "jobs.ashbyhq.com"
    as a prefix."""
    item_id = "ashby:acme:1b2c3d4e-0000-4000-8000-000000000001"
    spoofed = "https://jobs.ashbyhq.com\\acme\\1b2c3d4e-0000-4000-8000-000000000001"
    assert provider_identity(item_id, spoofed) is None


def test_trailing_dot_hostname_is_not_recognized() -> None:
    """ "jobs.ashbyhq.com." (a trailing-dot FQDN, DNS-equivalent to "jobs.ashbyhq.com") is compared
    as an exact string against the fixed host set and must fail closed: a false negative here is
    safe (no network call is ever made from identity derivation), but a false positive would let
    a non-whitelisted-looking host still prove identity."""
    item_id = "ashby:acme:1b2c3d4e-0000-4000-8000-000000000001"
    url = "https://jobs.ashbyhq.com./acme/1b2c3d4e-0000-4000-8000-000000000001"
    assert provider_identity(item_id, url) is None


def test_case_mismatched_provider_prefix_is_rejected() -> None:
    """`kind` is compared case-sensitively against the literal "greenhouse"/"lever"/"ashby"
    strings: an uppercase or mixed-case prefix must not be recognized (exact-identifier-only,
    ADR-008 §6)."""
    assert provider_identity("Greenhouse:acme:12345", None) is None
    assert provider_identity("GREENHOUSE:acme:12345", None) is None


# --- Fallback must never apply when the closing run itself is PARTIAL ---------------------------


def test_fallback_is_skipped_when_the_closing_run_is_partial(
    db: Session,
    feed_source: IngestionSource,
    gh_source: IngestionSource,
    web: FakeSource,
) -> None:
    """ADR-013 §5 fallback is derived inside the same `if run.invalid_count == 0 and
    run.error_count == 0` guard that gates closing records at all (pipeline.py `_process`): a
    run with even one unrelated invalid item must close nothing and must not hand canonical
    ownership back to a lower-authority source. This is the "fallback skipped when the run is
    partial" requirement from the review brief; there was no existing regression test for it."""
    feed_item = feed_job(
        f"greenhouse:{GREENHOUSE_BOARD}:1001",
        url="https://careers.example.com/robotics?gh_jid=1001",
    )
    web.json(FEED_URL, feed(feed_item))
    sync(db, feed_source, web)
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content="Board text.")))
    sync(db, gh_source, web)

    opportunity = db.scalars(select(Opportunity)).one()
    assert opportunity.description == "Board text."  # the board took over from the feed

    # Job 1001 is gone (would normally close and fall back to the feed) AND one item in the same
    # snapshot is malformed (missing the required "title"), making the run PARTIAL.
    web.json(GREENHOUSE_URL, greenhouse_board({"id": 2002, "absolute_url": None}))
    run = sync(db, gh_source, web)

    assert run.status is IngestionRunStatus.PARTIAL
    assert run.invalid_count == 1
    assert run.closed_count == 0  # nothing closed: a partial snapshot is never trusted

    gh_record = record(db, gh_source, "1001")
    assert gh_record.is_active is True  # still the owner, not closed

    db.refresh(opportunity)
    assert opportunity.description == "Board text."  # no fallback handed it back to the feed


def test_closed_record_keeps_last_canonical_text_with_no_remaining_automated_source(
    db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    """When the only automated record closes and nothing else is active, the opportunity closes
    (becomes unavailable) but keeps its last known canonical text rather than being blanked
    (ADR-013 §5, "existing behavior")."""
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content="Board text.")))
    sync(db, gh_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    assert opportunity.description == "Board text."

    web.json(GREENHOUSE_URL, greenhouse_board())
    run = sync(db, gh_source, web)

    assert run.closed_count == 1
    db.refresh(opportunity)
    assert opportunity.description == "Board text."  # kept, not erased
    gh_record = record(db, gh_source, "1001")
    assert gh_record.is_active is False
    assert gh_record.closed_at is not None


# --- sync_enabled_sources: one source failing never blocks or corrupts another ------------------


def test_one_source_erroring_does_not_stop_or_partially_commit_another(
    db: Session,
    feed_source: IngestionSource,
    gh_source: IngestionSource,
    web: FakeSource,
) -> None:
    """A totally broken source (unparseable snapshot) must not prevent a healthy source in the
    same `sync_enabled_sources` batch from completing a normal, successful sync (ADR-008 §4)."""
    web.respond(GREENHOUSE_URL, lambda _r: httpx2.Response(500))
    web.json(FEED_URL, feed(feed_job("workday:example:/job/A")))

    runs = sync_enabled_sources(db, transport=web.transport())

    by_source = {run.source_id: run for run in runs}
    assert by_source[gh_source.id].status is IngestionRunStatus.FAILED
    assert by_source[feed_source.id].status is IngestionRunStatus.SUCCESS
    assert db.scalars(select(Opportunity)).one().title == "Synthetic Engineering Intern"
