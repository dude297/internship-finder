"""ADR-015 listing freshness: the pure derivation."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

import pytest

from app.enums import OpportunitySourceType
from app.models import OpportunitySourceRecord
from app.services.freshness import SourceEvidence, derive_freshness
from app.services.source_health import SourceHealthStatus

NOW = datetime(2026, 10, 5, 12, tzinfo=UTC)
TODAY = NOW.date()
ATS, FEED, REGISTRY, CAREER, MANUAL = (
    OpportunitySourceType.ATS,
    OpportunitySourceType.PUBLIC_FEED,
    OpportunitySourceType.CURATED_REGISTRY,
    OpportunitySourceType.CAREER_PAGE,
    OpportunitySourceType.MANUAL,
)


@dataclass
class Record:
    ingestion_source_id: uuid.UUID | None
    is_active: bool
    source_type: OpportunitySourceType


def _source(health: SourceHealthStatus, hours_ago: float | None = 2) -> tuple[uuid.UUID, Any]:
    at = None if hours_ago is None else NOW - timedelta(hours=hours_ago)
    return uuid.uuid4(), SourceEvidence(health, at)


def _derive(
    records: list[Record], sources: dict[uuid.UUID, Any], verify_by: date | None = None
) -> Any:
    return derive_freshness(cast(list[OpportunitySourceRecord], records), sources, verify_by, TODAY)


def test_manual_and_closed() -> None:
    assert _derive([Record(None, True, MANUAL)], {}).state == "manual"
    sid, ev = _source("healthy")
    assert _derive([Record(sid, False, ATS)], {sid: ev}).state == "closed"


@pytest.mark.parametrize("direct", [ATS, CAREER])
def test_healthy_direct_source_is_direct_verified(direct: OpportunitySourceType) -> None:
    sid, ev = _source("healthy", 3)
    result = _derive([Record(sid, True, direct)], {sid: ev})
    assert result.state == "direct_verified"
    assert result.checked_at == NOW - timedelta(hours=3)


@pytest.mark.parametrize("health", ["warning", "stale", "failing", "disabled", "never_run"])
def test_unhealthy_direct_only_is_source_warning(health: SourceHealthStatus) -> None:
    sid, ev = _source(health, 30)
    result = _derive([Record(sid, True, ATS)], {sid: ev})
    assert result.state == "source_warning"
    assert result.checked_at is None


def test_partial_ats_with_healthy_feed_is_feed_current() -> None:
    ats, ats_ev = _source("warning")
    feed, feed_ev = _source("healthy", 4)
    result = _derive(
        [Record(ats, True, ATS), Record(feed, True, FEED)], {ats: ats_ev, feed: feed_ev}
    )
    assert result.state == "feed_current"
    assert result.checked_at == NOW - timedelta(hours=4)


def test_healthy_ats_beats_feed_and_uses_its_own_time() -> None:
    ats, ats_ev = _source("healthy", 5)
    feed, feed_ev = _source("healthy", 1)
    result = _derive(
        [Record(ats, True, ATS), Record(feed, True, FEED)], {ats: ats_ev, feed: feed_ev}
    )
    assert result.state == "direct_verified"
    assert result.checked_at == NOW - timedelta(hours=5)


def test_closed_ats_record_does_not_count() -> None:
    ats, ats_ev = _source("healthy")
    feed, feed_ev = _source("failing", None)
    records = [Record(ats, False, ATS), Record(feed, True, FEED)]
    assert _derive(records, {ats: ats_ev, feed: feed_ev}).state == "source_warning"


def test_registry_listed_and_recheck() -> None:
    reg, reg_ev = _source("healthy", 6)
    records = [Record(reg, True, REGISTRY)]
    listed = _derive(records, {reg: reg_ev}, TODAY + timedelta(days=1))
    assert (listed.state, listed.checked_at) == ("program_listed", NOW - timedelta(hours=6))
    assert _derive(records, {reg: reg_ev}, TODAY).state == "program_recheck"
    assert _derive(records, {reg: reg_ev}, None).state == "program_listed"


def test_registry_with_unhealthy_registry_source_is_warning() -> None:
    reg, reg_ev = _source("stale", 100)
    assert _derive([Record(reg, True, REGISTRY)], {reg: reg_ev}).state == "source_warning"


def test_unknown_source_is_not_trusted() -> None:
    assert _derive([Record(uuid.uuid4(), True, ATS)], {}).state == "source_warning"
