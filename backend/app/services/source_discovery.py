"""ATS source discovery and coverage (ADR-013 §2, §3). Derived on read from active discovery-feed
records already in the database; zero network calls, nothing stored.

A feed record only ever proves a board through `provider_identity` (the feed adapter's own
identity parser), so discovery can never disagree with deduplication (ADR-013 §2)."""

import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import cast
from urllib.parse import urlsplit

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import IngestionSourceKind, OpportunitySourceType, SourceRegion, SourceScope
from app.ingestion.adapters.community_feed import provider_identity
from app.ingestion.normalize import ASHBY, GREENHOUSE, LEVER, SMARTRECRUITERS, Identifier
from app.models import IngestionSource, Opportunity, OpportunitySourceRecord
from app.schemas.source_discovery import (
    CoverageMetrics,
    DiscoveryAddRequest,
    DiscoveryAddResponse,
    DiscoveryAddSkipped,
    ProviderCount,
    SourceDiscoveryResponse,
    SourceSuggestion,
    SupportedKind,
)
from app.services.sources import to_response, utcnow

# ADR-013 §2: the EU Greenhouse Job Board hosts aren't fetched (US API only), so a link naming
# one of them is unsupported even though the ID itself parses.
_EU_GREENHOUSE_HOSTS = {"boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io"}

# Fixed list of known feed ID prefixes (ADR-013 §8); anything else is "other". Never an arbitrary
# feed string.
_KNOWN_PROVIDERS = frozenset(
    {"greenhouse", "lever", "ashby", "workday", "oracle", "smartrecruiters", "workable", "rippling"}
)
_SUPPORTED_PROVIDERS = frozenset({"greenhouse", "lever", "ashby", "smartrecruiters"})

SuggestionKey = tuple[SupportedKind, str, SourceRegion | None]


class SourceDiscoveryConflict(Exception):
    """A concurrent request configured the same board first."""


def _suggestion_identity(external_id: str, source_url: str | None) -> SuggestionKey | None:
    """The (kind, identifier, region) a feed row proves, or None (ADR-013 §2)."""
    identity: Identifier | None = provider_identity(external_id, source_url)
    if identity is None:
        return None
    if identity.namespace == GREENHOUSE:
        host = (urlsplit(source_url or "").hostname or "").lower()
        if host in _EU_GREENHOUSE_HOSTS:
            return None
        board, _, _job = identity.value.partition(":")
        return IngestionSourceKind.GREENHOUSE, board, None
    if identity.namespace == LEVER:
        region, site, _posting = identity.value.split(":")
        return IngestionSourceKind.LEVER, site, SourceRegion(region)
    if identity.namespace == ASHBY:
        board, _, _posting = identity.value.partition(":")
        return IngestionSourceKind.ASHBY, board, None
    if identity.namespace == SMARTRECRUITERS:
        company, _, _posting = identity.value.partition(":")
        return IngestionSourceKind.SMARTRECRUITERS, company, None
    return None


def _key(kind: SupportedKind, identifier: str, region: SourceRegion | None) -> str:
    """Same format as IngestionSource.key."""
    parts = [kind.value, *([region.value] if region else []), identifier]
    return ":".join(parts)


def _provider_prefix(external_id: str) -> str:
    prefix = external_id.split(":", 1)[0].lower()
    return prefix if prefix in _KNOWN_PROVIDERS else "other"


def _uuid_set() -> set[uuid.UUID]:
    return set()


def _str_set() -> set[str]:
    return set()


def _str_counter() -> Counter[str]:
    return Counter()


@dataclass
class _SuggestionAgg:
    opportunity_ids: set[uuid.UUID] = field(default_factory=_uuid_set)
    feed_only_ids: set[uuid.UUID] = field(default_factory=_uuid_set)
    titles: set[str] = field(default_factory=_str_set)
    companies: Counter[str] = field(default_factory=_str_counter)


@dataclass
class _ProviderAgg:
    opportunities: int = 0
    enrichable: int = 0


def _display_name(companies: Counter[str], identifier: str) -> tuple[str, bool]:
    if not companies:
        return identifier[:200], False
    top = max(companies.values())
    winner = min((name for name, count in companies.items() if count == top))
    return winner[:200], len(companies) > 1


_record = OpportunitySourceRecord
# Mirrors app.services.discovery's `open` availability: an active automated record, or no
# automated record at all (managed by hand).
_automated = (
    select(_record.id)
    .correlate(Opportunity)
    .where(_record.opportunity_id == Opportunity.id, _record.ingestion_source_id.is_not(None))
)
_active = _automated.where(_record.is_active)
_open = or_(exists(_active), ~exists(_automated))
_active_ats = _active.where(_record.source_type == OpportunitySourceType.ATS)
_active_non_feed = _active.where(_record.source_type != OpportunitySourceType.PUBLIC_FEED)


def _coverage_row(db: Session) -> tuple[int, int, int, int]:
    """active_opportunities, with_description, ats_backed, feed_only (one query)."""
    has_text = func.length(func.btrim(Opportunity.description)) > 0
    row = db.execute(
        select(
            func.count(),
            func.count().filter(Opportunity.description.is_not(None), has_text),
            func.count().filter(exists(_active_ats)),
            func.count().filter(exists(_active), ~exists(_active_non_feed)),
        )
        .select_from(Opportunity)
        .where(_open)
    ).one()
    return row[0], row[1], row[2], row[3]


def _feed_rows(
    db: Session,
) -> list[tuple[str | None, str | None, str | None, uuid.UUID, str, bool]]:
    """One row per ACTIVE record of a built-in community_feed source: external_id, source_url,
    the feed's company label, the opportunity id/title, and whether the opportunity also has an
    active ATS record. Never the raw payload (only one JSON key is extracted, in SQL)."""
    company = _record.raw_payload.op("->>")("company")
    has_ats = exists(_active_ats)
    rows = db.execute(
        select(
            _record.external_id,
            _record.source_url,
            company,
            Opportunity.id,
            Opportunity.title,
            has_ats,
        )
        .join(IngestionSource, IngestionSource.id == _record.ingestion_source_id)
        .join(Opportunity, Opportunity.id == _record.opportunity_id)
        .where(
            IngestionSource.kind == IngestionSourceKind.COMMUNITY_FEED,
            _record.is_active,
            _record.external_id.is_not(None),
        )
    ).all()
    return [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows]


def _configured_keys(db: Session) -> set[SuggestionKey]:
    rows = db.execute(
        select(IngestionSource.kind, IngestionSource.identifier, IngestionSource.region).where(
            IngestionSource.kind.not_in(
                (IngestionSourceKind.COMMUNITY_FEED, IngestionSourceKind.CURATED_REGISTRY)
            )
        )
    ).all()
    return {(cast(SupportedKind, kind), identifier, region) for kind, identifier, region in rows}


def discover(db: Session) -> SourceDiscoveryResponse:
    """Zero network calls. Three queries total, regardless of catalog size."""
    active_opportunities, with_description, ats_backed, feed_only_sql = _coverage_row(db)
    rows = _feed_rows(db)
    configured = _configured_keys(db)

    suggestions: dict[SuggestionKey, _SuggestionAgg] = {}
    providers: dict[str, _ProviderAgg] = {}
    enrichable_total = 0

    for external_id, source_url, company, opp_id, title, has_ats in rows:
        if external_id is None:  # excluded by the query's WHERE; guards the type checker only
            continue
        identity = _suggestion_identity(external_id, source_url)
        if not has_ats:
            provider = _provider_prefix(external_id)
            agg = providers.setdefault(provider, _ProviderAgg())
            agg.opportunities += 1
            if identity is not None:
                agg.enrichable += 1
                enrichable_total += 1
        if identity is None:
            continue
        suggestion = suggestions.setdefault(identity, _SuggestionAgg())
        suggestion.opportunity_ids.add(opp_id)
        if not has_ats:
            suggestion.feed_only_ids.add(opp_id)
        suggestion.titles.add(title)
        if company and company.strip():
            suggestion.companies[company.strip()] += 1

    suggestion_list: list[SourceSuggestion] = []
    for (kind, identifier, region), agg in suggestions.items():
        name, ambiguous = _display_name(agg.companies, identifier)
        suggestion_list.append(
            SourceSuggestion(
                kind=kind,
                identifier=identifier,
                region=region,
                key=_key(kind, identifier, region),
                suggested_display_name=name,
                display_name_ambiguous=ambiguous,
                matching_opportunities=len(agg.opportunity_ids),
                feed_only_opportunities=len(agg.feed_only_ids),
                already_configured=(kind, identifier, region) in configured,
                sample_titles=sorted(agg.titles)[:3],
            )
        )
    suggestion_list.sort(key=lambda s: (-s.matching_opportunities, s.key))

    provider_list = [
        ProviderCount(
            provider=provider,
            supported=provider in _SUPPORTED_PROVIDERS,
            opportunities=agg.opportunities,
            enrichable=agg.enrichable,
        )
        for provider, agg in providers.items()
    ]
    provider_list.sort(key=lambda p: (-p.opportunities, p.provider))

    coverage = CoverageMetrics(
        active_opportunities=active_opportunities,
        with_description=with_description,
        without_description=active_opportunities - with_description,
        description_coverage_percent=(
            round(with_description / active_opportunities * 100, 1)
            if active_opportunities
            else None
        ),
        ats_backed=ats_backed,
        feed_only=feed_only_sql,
        enrichable=enrichable_total,
        unsupported=feed_only_sql - enrichable_total,
    )
    return SourceDiscoveryResponse(
        coverage=coverage, providers=provider_list, suggestions=suggestion_list
    )


def add_from_discovery(db: Session, request: DiscoveryAddRequest) -> DiscoveryAddResponse:
    """Re-runs discovery (trusted) and validates every selection against it; all-or-nothing.

    Raises ValueError (422) for a duplicate selection or one that isn't a current suggestion.
    Raises SourceDiscoveryConflict (409) when a concurrent request configured it first. Never
    syncs the created sources."""
    seen: set[SuggestionKey] = set()
    for selection in request.sources:
        selection_key: SuggestionKey = (selection.kind, selection.identifier, selection.region)
        if selection_key in seen:
            raise ValueError(f"Duplicate selection: {_key(*selection_key)}")
        seen.add(selection_key)

    current = discover(db)
    by_key: dict[SuggestionKey, SourceSuggestion] = {
        (s.kind, s.identifier, s.region): s for s in current.suggestions
    }

    skipped: list[DiscoveryAddSkipped] = []
    to_create: list[SourceSuggestion] = []
    for selection in request.sources:
        selection_key = (selection.kind, selection.identifier, selection.region)
        suggestion = by_key.get(selection_key)
        if suggestion is None:
            raise ValueError(f"{_key(*selection_key)} is not a current suggestion.")
        if suggestion.already_configured:
            skipped.append(DiscoveryAddSkipped(key=suggestion.key, reason="already_configured"))
            continue
        to_create.append(suggestion)

    created_sources: list[IngestionSource] = []
    try:
        for suggestion in to_create:
            source = IngestionSource(
                kind=suggestion.kind,
                identifier=suggestion.identifier,
                region=suggestion.region,
                display_name=suggestion.suggested_display_name,
                scope=SourceScope.INTERNSHIPS_ONLY,
            )
            db.add(source)
            created_sources.append(source)
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise SourceDiscoveryConflict("One of these boards was just configured.") from error

    created = [to_response(s, None, None, 0, utcnow()) for s in created_sources]
    return DiscoveryAddResponse(created=created, skipped=skipped)


__all__ = [
    "SupportedKind",
    "SourceDiscoveryConflict",
    "discover",
    "add_from_discovery",
]
