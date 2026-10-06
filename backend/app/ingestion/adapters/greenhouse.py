"""Greenhouse Job Board API: public, unauthenticated GETs on boards-api.greenhouse.io only.
Published jobs only; applications are never submitted through the API."""

import re
import time
from typing import Any, cast
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict

from app.enums import OpportunitySourceType
from app.ingestion.adapters import Adapter, CollectRequest, SourceConfig, normalize_each, top_level
from app.ingestion.http import FetchError, fetch_json
from app.ingestion.normalize import (
    GREENHOUSE,
    SLUG,
    Identifier,
    NormalizedOpportunity,
    Snapshot,
    SnapshotError,
    classify_opportunity_type,
    html_to_text,
    is_internship_title,
    parse_timestamp,
    url_identifier,
)

API = "https://boards-api.greenhouse.io/v1/boards"
# Public board pages whose first path segment is the board token.
BOARD_HOSTS = frozenset({"boards.greenhouse.io", "job-boards.greenhouse.io"})

# Large-board bounds (ADR-022). The per-request cap (http.MAX_BYTES, 20 MiB) is unchanged: the
# `?content=true` list of a ~2,500-job board is ~30 MiB, so a board whose content-free list shows
# more than LARGE_BOARD_JOBS jobs is never fetched with content. Its complete snapshot is the
# content-free list (~1 KiB/job); descriptions come from one small detail request per
# internship-titled job (any scope: other titles stay description-less, they aren't scored).
LARGE_BOARD_JOBS = 500  # at or below: one `?content=true` list as before (<= ~6 MiB observed)
MAX_JOBS = 10_000  # above: SnapshotError (a 10,000-job content-free list is ~10 MiB)
MAX_DETAIL_FETCHES = 100  # detail requests per run; the rest keep stored text, retried next run
MAX_DETAIL_BYTES = 1024 * 1024  # per detail response (observed ~10 KiB)
MAX_DETAIL_TOTAL_BYTES = 8 * 1024 * 1024  # cumulative detail bytes per run
MAX_DETAIL_SECONDS = 120.0  # wall clock for the whole detail phase
MAX_CONSECUTIVE_DETAIL_FAILURES = 5  # a failing provider isn't hit 100 times


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
        # Credentials or a port mean it isn't a plain public board link: refuse, don't strip.
        if (
            (parts.hostname or "").lower() not in BOARD_HOSTS
            or not segments
            or parts.username is not None
            or parts.port is not None
        ):
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
        opportunity_type=classify_opportunity_type(job.title),
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


def _list_url(source: SourceConfig) -> str:
    return f"{API}/{quote(source.identifier, safe='')}/jobs"


def _detail(job_id: int, request: CollectRequest) -> tuple[str, int]:
    """One job's `content` and the bytes it cost. Raises FetchError or LookupError."""
    url = f"{_list_url(request.source)}/{job_id}"
    fetched = fetch_json(url, transport=request.transport, max_bytes=MAX_DETAIL_BYTES)
    data = fetched.data
    if not isinstance(data, dict) or cast(dict[str, Any], data).get("id") != job_id:
        raise LookupError("detail names another job")
    content = cast(dict[str, Any], data).get("content")
    if not isinstance(content, str):
        raise LookupError("detail has no content")
    return content, fetched.size


def collect(request: CollectRequest) -> Any:
    """The complete snapshot is always the content-free list (checked against `meta.total`).
    On a large board descriptions are best-effort enrichment and never affect completeness: a
    job whose detail isn't fetched keeps its stored text (or has none) and is never closed."""
    source = request.source
    board = top_level(
        _Board, fetch_json(_list_url(source), transport=request.transport).data, "Greenhouse board"
    )
    jobs = board.jobs
    total = board.meta.total if board.meta else None
    if total is not None and total != len(jobs):
        raise SnapshotError(
            "incomplete_snapshot", f"The board declared {total} jobs but returned {len(jobs)}."
        )
    if len(jobs) > MAX_JOBS:
        raise SnapshotError("too_many_jobs", f"The board lists more than {MAX_JOBS} jobs.")
    if len(jobs) <= LARGE_BOARD_JOBS:  # chosen by list size, never by catching a huge download
        return fetch_json(_url(source), transport=request.transport).data
    if total is None:
        raise SnapshotError("incomplete_snapshot", "A large board didn't declare its job count.")

    seen: set[int] = set()
    entries: list[Any] = []
    pending: list[tuple[int, dict[str, Any]]] = []
    for item in jobs:
        if not isinstance(item, dict):
            entries.append(item)  # parse reports it as an invalid item
            continue
        job = dict(cast(dict[str, Any], item))
        job.pop("content", None)
        entries.append(job)
        job_id, title = job.get("id"), job.get("title")
        if not isinstance(job_id, int) or isinstance(job_id, bool):
            continue  # parse reports it
        if job_id in seen:
            raise SnapshotError("inconsistent_listing", "A job was listed twice.")
        seen.add(job_id)
        stored = request.known.get(str(job_id))
        old = cast(dict[str, Any], stored) if isinstance(stored, dict) else {}
        if isinstance(old.get("content"), str):
            job["content"] = old["content"]  # survives a failed or deferred refetch
            if old.get("updated_at") == job.get("updated_at"):
                continue
        if isinstance(title, str) and is_internship_title(title):
            pending.append((job_id, job))

    started = time.monotonic()
    fetches = spent = failures = 0
    for job_id, job in pending:
        if (
            fetches >= MAX_DETAIL_FETCHES
            or spent >= MAX_DETAIL_TOTAL_BYTES
            or failures >= MAX_CONSECUTIVE_DETAIL_FAILURES
            or time.monotonic() - started > MAX_DETAIL_SECONDS
        ):
            break
        fetches += 1
        try:
            job["content"], size = _detail(job_id, request)
        except (FetchError, LookupError):
            failures += 1
            continue
        failures = 0
        spent += size
    return {"jobs": entries, "meta": {"total": len(entries)}}


ADAPTER = Adapter(
    source_type=OpportunitySourceType.ATS,
    url=_url,
    parse=parse,
    normalize=_normalize,
    collect=collect,
)
