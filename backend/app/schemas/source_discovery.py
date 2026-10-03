"""Source coverage and discovery (ADR-013 §2, §3): derived on read from existing records, never
stored. Counts and public posting metadata only; never raw payloads."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.enums import IngestionSourceKind, SourceRegion
from app.schemas.sources import SourceResponse

SupportedKind = Literal[
    IngestionSourceKind.GREENHOUSE, IngestionSourceKind.LEVER, IngestionSourceKind.ASHBY
]

MAX_DISCOVERY_ADD = 25


class CoverageMetrics(BaseModel):
    """Over open opportunities (the opportunity list's default `open` availability)."""

    active_opportunities: int
    # Non-empty canonical description.
    with_description: int
    without_description: int
    # with_description / active_opportunities * 100, one decimal; None when there are none.
    description_coverage_percent: float | None
    # An active record from a direct ATS source (Greenhouse, Lever, Ashby).
    ats_backed: int
    # Active automated records, all of them from the discovery feed.
    feed_only: int
    # Feed-only, and the feed proves a supported provider identity (a suggestion covers it).
    enrichable: int
    # Feed-only without a supported, proven provider identity (Workday, Oracle, unknown, ...).
    unsupported: int


class ProviderCount(BaseModel):
    """Feed-only open opportunities by the provider named in the feed ID's prefix."""

    # greenhouse | lever | ashby | workday | oracle | smartrecruiters | workable | rippling |
    # other. Never an arbitrary feed string.
    provider: str
    supported: bool
    opportunities: int
    # Of those, how many have an exact, proven identity a suggestion covers (supported only).
    enrichable: int


class SourceSuggestion(BaseModel):
    kind: SupportedKind
    identifier: str
    region: SourceRegion | None
    # Same format as IngestionSource.key, e.g. greenhouse:board, lever:eu:site, ashby:board.
    key: str
    # The feed's company label: a suggestion for a human-readable name, never identity.
    suggested_display_name: str
    # Feed rows for this board disagree on the company label (the most common one is chosen;
    # ties alphabetically).
    display_name_ambiguous: bool
    # Open opportunities whose active feed record proves this board/site.
    matching_opportunities: int
    # Of those, how many are still feed-only.
    feed_only_opportunities: int
    already_configured: bool
    # At most 3 canonical titles, alphabetical.
    sample_titles: list[str]


class SourceDiscoveryResponse(BaseModel):
    coverage: CoverageMetrics
    # Sorted by opportunities descending, then provider.
    providers: list[ProviderCount]
    # Sorted by matching_opportunities descending, then key.
    suggestions: list[SourceSuggestion]


class DiscoverySelection(BaseModel):
    """One suggestion, by identity only. The server re-derives it from trusted records; any
    display name, URL, or other hidden field is refused (extra="forbid")."""

    model_config = ConfigDict(extra="forbid")

    kind: SupportedKind
    identifier: str = Field(min_length=1, max_length=64)
    region: SourceRegion | None = None


class DiscoveryAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[DiscoverySelection] = Field(min_length=1, max_length=MAX_DISCOVERY_ADD)


class DiscoveryAddSkipped(BaseModel):
    key: str
    reason: Literal["already_configured"]


class DiscoveryAddResponse(BaseModel):
    created: list[SourceResponse]
    skipped: list[DiscoveryAddSkipped]
