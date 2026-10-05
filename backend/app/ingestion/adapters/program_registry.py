"""The curated program registry (ADR-014 §5-§8): a repository data file of public program facts,
read from disk (no network) and written through the shared pipeline like any other source.

Entries carry only a `curated:<slug>:<cycle>` identifier -- deliberately no URL identifier, so a
program page equal to a feed link can never merge a program into an unrelated posting."""

import json
import re
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal, Self, cast
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.enums import OpportunitySourceType, OpportunityType, RemoteMode
from app.ingestion.adapters import (
    Adapter,
    CollectRequest,
    SourceConfig,
    normalize_each,
    top_level,
)
from app.ingestion.normalize import (
    CURATED,
    Identifier,
    NormalizedOpportunity,
    Snapshot,
    SnapshotError,
)

BUILTIN_IDENTIFIER = "program-registry"
REGISTRY_PATH = Path(__file__).resolve().parents[3] / "data" / "program_registry.json"
MAX_FILE_BYTES = 1024 * 1024

# Rust regex (pydantic): "$" matches only at the very end of the text, never before a newline.
_SLUG = r"^[a-z0-9][a-z0-9-]{1,62}$"
_CYCLE = r"^20[0-9]{2}(-[a-z]{3,10})?$"


def _https_url(value: str) -> str:
    """https only, a dotted hostname, no userinfo, no port, no whitespace, at most 2048 chars."""
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as error:
        raise ValueError("not a valid URL") from error
    if (
        len(value) > 2048
        or re.search(r"\s", value)
        or parts.scheme != "https"
        or "." not in (parts.hostname or "")
        or parts.username is not None
        or parts.password is not None
        or port is not None
    ):
        raise ValueError("must be a plain https URL")
    return value


Url = Annotated[str, AfterValidator(_https_url)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Verified(_Strict):
    open_date: date | None = None
    deadline: date | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        return self


class Program(_Strict):
    slug: Annotated[str, Field(pattern=_SLUG)]
    cycle: Annotated[str, Field(max_length=20, pattern=_CYCLE)]
    title: Annotated[str, Field(min_length=1, max_length=300)]
    organization: Annotated[str, Field(min_length=1, max_length=200)]
    opportunity_type: OpportunityType
    application_url: Url | None = None
    source_url: Url
    location: Annotated[str, Field(max_length=200)] | None = None
    remote_mode: RemoteMode | None = None
    verified: _Verified
    typical_open_window: Annotated[str, Field(max_length=100)] | None = None
    typical_close_window: Annotated[str, Field(max_length=100)] | None = None
    verify_by: date | None = None
    eligibility_summary: Annotated[str, Field(max_length=1000)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=2000)]
    last_verified: date


class _Registry(_Strict):
    schema_version: Literal[1]
    programs: list[Any]


def _check_top_level(payload: Any) -> _Registry:
    registry = top_level(_Registry, payload, "program registry")
    seen: set[tuple[Any, Any]] = set()
    for item in registry.programs:
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, Any], item)
        key = (entry.get("slug"), entry.get("cycle"))
        if key in seen:
            raise SnapshotError("duplicate_entry", "The program registry repeats a slug and cycle.")
        seen.add(key)
    return registry


def _normalize(raw: dict[str, Any], source: SourceConfig) -> NormalizedOpportunity:
    program = Program.model_validate(raw)
    identity = f"{program.slug}:{program.cycle}"
    description = program.description
    if program.eligibility_summary:
        description += "\n\nEligibility (summary): " + program.eligibility_summary
    verified = program.verified
    return NormalizedOpportunity(
        external_id=identity,
        identifiers=(Identifier(namespace=CURATED, value=identity),),
        title=program.title,
        organization=program.organization,
        description=description,
        opportunity_type=program.opportunity_type,
        application_url=program.application_url or program.source_url,
        location=program.location,
        remote_mode=program.remote_mode,
        application_deadline=verified.deadline,
        start_date=verified.start_date,
        end_date=verified.end_date,
        program_cycle=program.cycle,
        typical_open_window=program.typical_open_window,
        typical_close_window=program.typical_close_window,
        verify_by=program.verify_by,
        raw_payload=raw,
    )


def parse(payload: Any, source: SourceConfig) -> Snapshot:
    registry = _check_top_level(payload)
    return Snapshot(
        items=normalize_each(
            registry.programs,
            lambda raw: _normalize(raw, source),
            lambda raw: f"{raw.get('slug')}:{raw.get('cycle')}",
        )
    )


def collect(request: CollectRequest) -> Any:
    """Read the bundled file; no network. Unreadable or malformed → the run fails, nothing
    changes (no partial registry)."""
    try:
        with REGISTRY_PATH.open("rb") as file:
            data = file.read(MAX_FILE_BYTES + 1)
    except OSError as error:
        raise SnapshotError(
            "registry_unreadable", "The program registry file is unreadable."
        ) from error
    if len(data) > MAX_FILE_BYTES:
        raise SnapshotError("too_large", "The program registry file is too large.")
    try:
        payload: Any = json.loads(data.decode("utf-8"))
    except ValueError as error:  # JSONDecodeError and UnicodeDecodeError
        raise SnapshotError("invalid_json", "The program registry isn't valid JSON.") from error
    _check_top_level(payload)
    return payload


ADAPTER = Adapter(
    source_type=OpportunitySourceType.CURATED_REGISTRY,
    url=lambda _source: "",
    parse=parse,
    normalize=_normalize,
    collect=collect,
)
