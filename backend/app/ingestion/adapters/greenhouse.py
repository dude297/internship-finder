"""Greenhouse Job Board API: public, unauthenticated GETs on boards-api.greenhouse.io only.
Published jobs only; applications are never submitted through the API."""

import re
from typing import Any
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict

from app.enums import OpportunitySourceType
from app.ingestion.adapters import Adapter, SourceConfig, normalize_each, top_level
from app.ingestion.normalize import (
    GREENHOUSE,
    SLUG,
    Identifier,
    NormalizedOpportunity,
    Snapshot,
    SnapshotError,
    html_to_text,
    parse_timestamp,
    url_identifier,
)

API = "https://boards-api.greenhouse.io/v1/boards"
# Public board pages whose first path segment is the board token.
BOARD_HOSTS = frozenset({"boards.greenhouse.io", "job-boards.greenhouse.io"})


class _Location(BaseModel):
    name: str | None = None


class _Job(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    title: str
    absolute_url: str | None = None
    location: _Location | None = None
    updated_at: str | None = None
    first_published: str | None = None
    content: str | None = None


class _Meta(BaseModel):
    total: int | None = None


class _Board(BaseModel):
    jobs: list[Any]
    meta: _Meta | None = None


def parse_board_reference(value: str) -> str:
    """A board token from a token or a public board URL (boards./job-boards.greenhouse.io).
    Only the token is kept; the URL itself is never requested. Raises ValueError."""
    text = value.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE) and "/" in text:
        text = f"https://{text}"
    if "://" in text:
        parts = urlsplit(text)
        segments = [s for s in parts.path.split("/") if s]
        if (parts.hostname or "").lower() not in BOARD_HOSTS or not segments:
            raise ValueError(
                "Use a Greenhouse board link like https://job-boards.greenhouse.io/<board>"
            )
        text = segments[0]
    token = text.lower()
    if not SLUG.match(token):
        raise ValueError("That isn't a valid Greenhouse board token.")
    return token


def _normalize(raw: dict[str, Any], source: SourceConfig) -> NormalizedOpportunity:
    job = _Job.model_validate(raw)
    return NormalizedOpportunity(
        external_id=str(job.id),
        identifiers=(
            Identifier(namespace=GREENHOUSE, value=f"{source.identifier}:{job.id}"),
            *url_identifier(job.absolute_url),
        ),
        title=job.title,
        organization=source.display_name,
        description=html_to_text(job.content, entity_escaped=True),
        application_url=job.absolute_url,
        location=job.location.name if job.location else None,
        # first_published is when the posting went live; updated_at is not a posting date.
        posted_at=parse_timestamp(job.first_published),
        source_published_at=parse_timestamp(job.first_published),
        source_updated_at=parse_timestamp(job.updated_at),
        raw_payload=raw,
    )


def parse(payload: Any, source: SourceConfig) -> Snapshot:
    board = top_level(_Board, payload, "Greenhouse board")
    total = board.meta.total if board.meta else None
    if total is not None and total != len(board.jobs):
        raise SnapshotError(
            "incomplete_snapshot",
            f"The board declared {total} jobs but returned {len(board.jobs)}.",
        )
    return Snapshot(
        items=normalize_each(
            board.jobs, lambda job: _normalize(job, source), lambda job: job.get("id")
        )
    )


def _url(source: SourceConfig) -> str:
    return f"{API}/{quote(source.identifier, safe='')}/jobs?content=true"


ADAPTER = Adapter(source_type=OpportunitySourceType.ATS, url=_url, parse=parse)
