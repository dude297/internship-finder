"""Ashby Job Postings API: public, unauthenticated GETs on api.ashbyhq.com only (ADR-012 §12).
Never the authenticated job.list/jobPosting.list API; applications are never submitted.

Board names are case-insensitive at the provider (verified against the live public endpoint:
`/posting-api/job-board/Ashby`, `/ASHBY`, and `/aShBy` all resolve to the same board, though the
canonical `jobUrl` keeps the owner's original casing). We therefore lowercase and store the board
name, like the Greenhouse token and the Lever site slug."""

import re
from typing import Any, cast
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict, Field

from app.enums import OpportunitySourceType, RemoteMode
from app.ingestion.adapters import Adapter, SourceConfig, normalize_each, top_level
from app.ingestion.normalize import (
    ASHBY,
    SLUG,
    Identifier,
    NormalizedOpportunity,
    Snapshot,
    classify_opportunity_type,
    html_to_text,
    parse_timestamp,
    url_identifier,
)

API = "https://api.ashbyhq.com/posting-api/job-board"
BOARD_HOST = "jobs.ashbyhq.com"
_WORKPLACE = {"onsite": RemoteMode.ONSITE, "remote": RemoteMode.REMOTE, "hybrid": RemoteMode.HYBRID}


class _SecondaryLocation(BaseModel):
    model_config = ConfigDict(extra="allow")

    location: str | None = None


class _Job(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=255)
    title: str
    employmentType: str | None = None  # noqa: N815 -- Ashby's field name
    location: str | None = None
    secondaryLocations: list[_SecondaryLocation] = Field(  # noqa: N815
        default_factory=list[_SecondaryLocation]
    )
    workplaceType: str | None = None  # noqa: N815
    isRemote: bool | None = None  # noqa: N815
    # Missing only on malformed/legacy payloads; the live public endpoint always sends it, and
    # our own manual check confirmed it's always present. Treated as listed to fail open rather
    # than silently dropping a posting on an unexpected shape (ADR-012 §12).
    isListed: bool | None = None  # noqa: N815
    publishedAt: str | None = None  # noqa: N815
    jobUrl: str | None = None  # noqa: N815
    applyUrl: str | None = None  # noqa: N815
    descriptionHtml: str | None = None  # noqa: N815
    descriptionPlain: str | None = None  # noqa: N815


class _Board(BaseModel):
    model_config = ConfigDict(extra="allow")

    jobs: list[Any]
    apiVersion: str | None = None  # noqa: N815


def parse_board_reference(value: str) -> str:
    """A board name from a name or the official hosted board URL (jobs.ashbyhq.com only). Only
    the name is kept; the URL itself is never requested. Raises ValueError."""
    text = value.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE) and "/" in text:
        text = f"https://{text}"
    if "://" in text:
        parts = urlsplit(text)
        segments = [s for s in parts.path.split("/") if s]
        # Credentials or a port mean it isn't a plain public board link: refuse, don't strip.
        if (
            (parts.hostname or "").lower() != BOARD_HOST
            or not segments
            or parts.username is not None
            or parts.port is not None
        ):
            raise ValueError("Use an Ashby board link like https://jobs.ashbyhq.com/<board>")
        text = segments[0]
    name = text.lower()
    if not SLUG.match(name):
        raise ValueError("That isn't a valid Ashby board name.")
    return name


def _remote_mode(job: "_Job") -> RemoteMode | None:
    # workplaceType is the structured signal; `isRemote: false` doesn't mean on-site (Ashby
    # still sets it false for hybrid roles), so only a true isRemote is unambiguous on its own.
    mapped = _WORKPLACE.get((job.workplaceType or "").lower())
    if mapped is not None:
        return mapped
    return RemoteMode.REMOTE if job.isRemote is True else None


def _normalize(raw: dict[str, Any], source: SourceConfig) -> NormalizedOpportunity:
    job = _Job.model_validate(raw)
    locations = [job.location, *(loc.location for loc in job.secondaryLocations)]
    description = job.descriptionPlain or html_to_text(job.descriptionHtml)
    published = parse_timestamp(job.publishedAt)
    return NormalizedOpportunity(
        external_id=job.id,
        identifiers=(
            Identifier(namespace=ASHBY, value=f"{source.identifier}:{job.id}"),
            # The posting page, not the apply page: a stable identity even if applications close.
            *url_identifier(job.jobUrl),
        ),
        title=job.title,
        organization=source.display_name,
        description=description,
        opportunity_type=classify_opportunity_type(
            job.title, structured_intern=job.employmentType == "Intern"
        ),
        # applyUrl goes straight to the application form; jobUrl is the posting page itself and
        # is what the owner wants to open and read first.
        application_url=job.jobUrl or job.applyUrl,
        location=" · ".join(loc for loc in locations if loc) or None,
        remote_mode=_remote_mode(job),
        posted_at=published,
        source_published_at=published,
        raw_payload=raw,
    )


def parse(payload: Any, source: SourceConfig) -> Snapshot:
    board = top_level(_Board, payload, "Ashby job board")

    # Unlisted postings are never imported, and are excluded before normalization so a complete
    # snapshot closes them exactly like a removed posting (ADR-012 §12); they don't count as
    # "filtered" since that counter is reserved for the internships_only scope filter.
    def _listed(job: Any) -> bool:
        # Exactly `true` (or absent): a string like "false" must never import a hidden posting.
        return not isinstance(job, dict) or cast(dict[str, Any], job).get("isListed", True) is True

    listed: list[Any] = [job for job in board.jobs if _listed(job)]
    return Snapshot(
        items=normalize_each(listed, lambda job: _normalize(job, source), lambda job: job.get("id"))
    )


def _url(source: SourceConfig) -> str:
    return f"{API}/{quote(source.identifier, safe='')}?includeCompensation=false"


ADAPTER = Adapter(source_type=OpportunitySourceType.ATS, url=_url, parse=parse)
