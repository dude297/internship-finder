"""Feed-free bootstrap (ADR-016): a new installation becomes usable without the community feed.

Adds Direct Source Catalog entries through `direct_catalog.add_from_catalog` (the same path as
`POST /api/sources/catalog/add`), makes sure the curated registry source exists, and can disable
the feed. It never syncs; the caller decides.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import IngestionSourceKind, SourceScope
from app.models import IngestionSource, OpportunitySourceRecord
from app.models.ingestion import BUILTIN_KINDS
from app.schemas.source_discovery import MAX_DISCOVERY_ADD, DiscoveryAddRequest, DiscoverySelection
from app.services import direct_catalog
from app.services.source_discovery import configured_keys

# docs/operations.md "Operational source cap": enabled direct sources.
MAX_ENABLED_DIRECT_SOURCES = 100  # operations.md#operational-source-cap (raised 2026-10-09)


class BootstrapRefused(Exception):
    """Unknown tag, the cap would be exceeded, or the feed still has open postings."""


@dataclass
class BootstrapResult:
    selected: int = 0
    added: int = 0
    already_configured: int = 0
    registry_created: bool = False
    feed_disabled: bool = False


def _enabled_direct(db: Session) -> int:
    return (
        db.scalar(
            select(func.count()).where(
                IngestionSource.enabled,
                IngestionSource.kind.not_in([IngestionSourceKind(k) for k in BUILTIN_KINDS]),
            )
        )
        or 0
    )


def bootstrap_sources(
    db: Session, *, tags: Sequence[str] = (), disable_feed: bool = False, dry_run: bool = False
) -> BootstrapResult:
    """Raises BootstrapRefused. With dry_run nothing is written; otherwise the caller commits.
    Entries are all-or-nothing: the cap is checked before anything is added."""
    known_tags = {t for e in direct_catalog.catalog() for t in e.tags}
    if unknown := sorted(set(tags) - known_tags):
        raise BootstrapRefused(f"unknown tag(s): {', '.join(unknown)}")
    entries = [e for e in direct_catalog.catalog() if not tags or set(tags) & set(e.tags)]
    configured = configured_keys(db)
    fresh = [e for e in entries if e.key not in configured]
    if _enabled_direct(db) + len(fresh) > MAX_ENABLED_DIRECT_SOURCES:
        raise BootstrapRefused(
            f"would exceed the {MAX_ENABLED_DIRECT_SOURCES} enabled direct source cap; "
            "narrow with --tags"
        )
    feed = db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.COMMUNITY_FEED)
    ).first()
    if disable_feed and feed is not None and feed.enabled:
        active = db.scalar(
            select(func.count()).where(
                OpportunitySourceRecord.ingestion_source_id == feed.id,
                OpportunitySourceRecord.is_active,
            )
        )
        if active:
            raise BootstrapRefused("the feed has open postings; use retire-source feed instead")

    result = BootstrapResult(
        selected=len(entries), added=len(fresh), already_configured=len(entries) - len(fresh)
    )
    registry = db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.CURATED_REGISTRY)
    ).first()
    result.registry_created = registry is None
    result.feed_disabled = bool(disable_feed and feed is not None and feed.enabled)
    if dry_run:
        return result

    for i in range(0, len(fresh), MAX_DISCOVERY_ADD):
        selections = [
            DiscoverySelection(kind=e.kind, identifier=e.identifier, region=e.region)
            for e in fresh[i : i + MAX_DISCOVERY_ADD]
        ]
        direct_catalog.add_from_catalog(db, DiscoveryAddRequest(sources=selections))
    if registry is None:  # the migration seeds it; this only repairs a database without it
        db.add(
            IngestionSource(
                kind=IngestionSourceKind.CURATED_REGISTRY,
                identifier="program-registry",
                display_name="Curated Program Registry",
                scope=SourceScope.ALL,
            )
        )
    if result.feed_disabled and feed is not None:
        feed.enabled = False
    db.flush()
    return result
