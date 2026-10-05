"""The Direct Source Catalog (ADR-015 §6): owner-reviewable, officially verified source
CONFIGURATION (which company uses which public job board), never listing data and never another
tracker's data. It lets the app find direct sources without the community feed.

Entries are validated at load with the same identifier parsers the Add Source form uses, so a
catalog entry can never configure anything the owner couldn't type in by hand. Adding entries
goes through the same all-or-nothing creation as discovery suggestions; it never syncs and never
activates anything on its own.
"""

import json
from datetime import date
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import IngestionSourceKind, SourceRegion, SourceScope
from app.models import IngestionSource
from app.schemas.source_discovery import (
    DiscoveryAddRequest,
    DiscoveryAddResponse,
    DiscoveryAddSkipped,
    SupportedKind,
)
from app.services.source_discovery import (
    SourceDiscoveryConflict,
    SuggestionKey,
    configured_keys,
    suggestion_key,
)
from app.services.sources import parse_reference, to_response, utcnow

CATALOG_FILE = Path(__file__).resolve().parents[2] / "data" / "direct_source_catalog.json"

Tag = Literal[
    "faang",
    "ai",
    "software",
    "cloud",
    "fintech",
    "mobility",
    "marketplace",
    "hardware",
    "semiconductor",
    "semiconductor-equipment",
    "eda",
    "robotics",
    "aerospace",
    "research",
    "government",
]


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization: str = Field(min_length=1, max_length=200)
    kind: SupportedKind
    identifier: str = Field(min_length=1, max_length=64)
    region: SourceRegion | None = None
    careers_url: HttpUrl
    # How ownership was verified (official careers page and/or the provider's documented API).
    evidence: str = Field(min_length=1, max_length=500)
    verified_at: date
    tags: list[Tag] = Field(default_factory=list[Tag])

    @field_validator("careers_url")
    @classmethod
    def _https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("careers_url must be https")
        return value

    @property
    def key(self) -> SuggestionKey:
        return (self.kind, self.identifier, self.region)


class _CatalogFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    sources: list[CatalogEntry]


def load_catalog(path: Path = CATALOG_FILE) -> tuple[CatalogEntry, ...]:
    """Raises ValueError for an invalid file: an identifier the Add Source parser wouldn't
    produce verbatim, or a duplicate board."""
    data = _CatalogFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    seen: set[SuggestionKey] = set()
    for entry in data.sources:
        identifier, region = parse_reference(entry.kind, entry.identifier, entry.region)
        if (identifier, region) != (entry.identifier, entry.region):
            raise ValueError(f"Catalog entry {entry.organization} isn't in canonical form.")
        if entry.key in seen:
            raise ValueError(f"Duplicate catalog entry {suggestion_key(*entry.key)}.")
        seen.add(entry.key)
    return tuple(data.sources)


@cache
def catalog() -> tuple[CatalogEntry, ...]:
    return load_catalog()


class CatalogEntryResponse(BaseModel):
    key: str
    organization: str
    kind: SupportedKind
    identifier: str
    region: SourceRegion | None
    careers_url: str
    evidence: str
    verified_at: date
    tags: list[str]
    already_configured: bool


class CatalogResponse(BaseModel):
    entries: list[CatalogEntryResponse]


def list_catalog(db: Session) -> CatalogResponse:
    configured = configured_keys(db)
    entries = sorted(catalog(), key=lambda e: (e.organization.casefold(), suggestion_key(*e.key)))
    return CatalogResponse(
        entries=[
            CatalogEntryResponse(
                key=suggestion_key(*e.key),
                organization=e.organization,
                kind=e.kind,
                identifier=e.identifier,
                region=e.region,
                careers_url=str(e.careers_url),
                evidence=e.evidence,
                verified_at=e.verified_at,
                tags=list(e.tags),
                already_configured=e.key in configured,
            )
            for e in entries
        ]
    )


def add_from_catalog(db: Session, request: DiscoveryAddRequest) -> DiscoveryAddResponse:
    """Same contract as discovery add (ADR-013 §3): every selection must be a catalog entry;
    all-or-nothing; already-configured ones are skipped; never syncs.

    Raises ValueError (422) or SourceDiscoveryConflict (409)."""
    by_key = {e.key: e for e in catalog()}
    seen: set[SuggestionKey] = set()
    chosen: list[CatalogEntry] = []
    for selection in request.sources:
        key: SuggestionKey = (selection.kind, selection.identifier, selection.region)
        if key in seen:
            raise ValueError(f"Duplicate selection: {suggestion_key(*key)}")
        seen.add(key)
        entry = by_key.get(key)
        if entry is None:
            raise ValueError(f"{suggestion_key(*key)} is not in the direct source catalog.")
        chosen.append(entry)

    configured = configured_keys(db)
    skipped = [
        DiscoveryAddSkipped(key=suggestion_key(*e.key), reason="already_configured")
        for e in chosen
        if e.key in configured
    ]
    created: list[IngestionSource] = []
    try:
        for entry in chosen:
            if entry.key in configured:
                continue
            source = IngestionSource(
                kind=IngestionSourceKind(entry.kind),
                identifier=entry.identifier,
                region=entry.region,
                display_name=entry.organization,
                scope=SourceScope.INTERNSHIPS_ONLY,
            )
            db.add(source)
            created.append(source)
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise SourceDiscoveryConflict("One of these boards was just configured.") from error
    return DiscoveryAddResponse(
        created=[to_response(s, None, None, 0, utcnow()) for s in created], skipped=skipped
    )
