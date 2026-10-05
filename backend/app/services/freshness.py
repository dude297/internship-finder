"""Listing freshness (ADR-015): derived on read from source records and source health, never
stored. It says how strong the evidence is that an open opportunity is still listed, never that
it is definitely open.

`derive_freshness` is pure, so it's tested without a database or the wall clock.
"""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.enums import OpportunitySourceType
from app.models import OpportunitySourceRecord
from app.schemas.opportunity import FreshnessState
from app.services.source_health import SourceHealthStatus, derive_health
from app.services.sources import latest_finished_statuses, list_sources

NEEDS_REVIEW_STATES: frozenset[FreshnessState] = frozenset({"source_warning", "program_recheck"})

# The original posting's own source (ADR-013 §1 authority tier 0). CAREER_PAGE is the provenance
# a future approved first-party company source uses.
DIRECT_SOURCE_TYPES = frozenset({OpportunitySourceType.ATS, OpportunitySourceType.CAREER_PAGE})


@dataclass(frozen=True)
class SourceEvidence:
    health: SourceHealthStatus
    last_success_at: datetime | None


@dataclass(frozen=True)
class Freshness:
    state: FreshnessState
    # When the best evidence was last confirmed (its source's last complete success).
    checked_at: datetime | None


def derive_freshness(
    records: Iterable[OpportunitySourceRecord],
    sources: Mapping[uuid.UUID, SourceEvidence],
    verify_by: date | None,
    today: date,
) -> Freshness:
    automated = [r for r in records if r.ingestion_source_id is not None]
    if not automated:
        return Freshness("manual", None)
    active = [r for r in automated if r.is_active]
    if not active:
        return Freshness("closed", None)

    def latest_healthy(types: frozenset[OpportunitySourceType]) -> datetime | None:
        times = [
            evidence.last_success_at
            for r in active
            if r.source_type in types
            and r.ingestion_source_id is not None
            and (evidence := sources.get(r.ingestion_source_id)) is not None
            and evidence.health == "healthy"
            and evidence.last_success_at is not None
        ]
        return max(times) if times else None

    if (checked := latest_healthy(DIRECT_SOURCE_TYPES)) is not None:
        return Freshness("direct_verified", checked)
    if any(r.source_type is OpportunitySourceType.CURATED_REGISTRY for r in active):
        if verify_by is not None and verify_by <= today:
            return Freshness("program_recheck", None)
        registry = latest_healthy(frozenset({OpportunitySourceType.CURATED_REGISTRY}))
        if registry is not None:
            return Freshness("program_listed", registry)
    if (checked := latest_healthy(frozenset({OpportunitySourceType.PUBLIC_FEED}))) is not None:
        return Freshness("feed_current", checked)
    return Freshness("source_warning", None)


def source_evidence(db: Session, now: datetime) -> dict[uuid.UUID, SourceEvidence]:
    """Health of every source, in two queries regardless of catalog size (never per row)."""
    statuses = latest_finished_statuses(db)
    evidence: dict[uuid.UUID, SourceEvidence] = {}
    for source in list_sources(db):
        health = derive_health(
            enabled=source.enabled,
            latest_finished_status=statuses.get(source.id),
            last_success_at=source.last_success_at,
            consecutive_failures=0,
            now=now,
        )
        evidence[source.id] = SourceEvidence(health.health, source.last_success_at)
    return evidence


def healthy_source_ids(evidence: Mapping[uuid.UUID, SourceEvidence]) -> list[uuid.UUID]:
    return [source_id for source_id, e in evidence.items() if e.health == "healthy"]
