"""Workable's documented public widget API (ADR-015 §7): one keyless GET per account on
`www.workable.com` (workable.readme.io, "jobs"), which 302s to `apply.workable.com` (both hosts
are on the http.py allowlist). Applications are never submitted.

Closure: a 200 whose top level has a `jobs` list is the whole published board (no pagination), so
the pipeline closes absent shortcodes after the normal miss rule. An unknown or renamed account
answers 404 (observed live), which `fetch_json` raises as FetchError("not_found"): the run fails
and nothing closes. Only a 200 with an empty `jobs` list closes everything, and that is what a
real account with no open roles looks like, so it can't be told apart from a legitimate empty
board (same inherent limit as SmartRecruiters: renaming an account is the owner's error to fix).

Mapping notes: `published_on` (a date) is the posted date, midnight UTC; `created_at` is NOT used
(a draft can be created long before it is published). There is never a deadline. Remote mode is
set only when the payload says so (`telecommuting: true` or a `workplace_type`). Duplicate
shortcodes in one response are left to the pipeline (it records a duplicate_item error)."""

import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict, Field

from app.enums import OpportunitySourceType, RemoteMode
from app.ingestion.adapters import Adapter, SourceConfig, normalize_each, top_level
from app.ingestion.normalize import (
    SLUG,
    Identifier,
    NormalizedOpportunity,
    Snapshot,
    classify_opportunity_type,
    html_to_text,
    url_identifier,
)

API = "https://www.workable.com/api/accounts"
APPLY_HOST = "apply.workable.com"
WORKABLE = "workable"  # identifier namespace; values are `<account>:<SHORTCODE>`
_SHORTCODE = r"^[A-Za-z0-9]{4,32}$"  # Rust regex in pydantic: no \Z, and $ is end-only
_WORKPLACE = {
    "on_site": RemoteMode.ONSITE,
    "onsite": RemoteMode.ONSITE,
    "remote": RemoteMode.REMOTE,
    "hybrid": RemoteMode.HYBRID,
}
_LINK_ERROR = "Use a Workable link like https://apply.workable.com/<account>"


class _Location(BaseModel):
    model_config = ConfigDict(extra="allow")

    city: str | None = None
    region: str | None = None
    country: str | None = None


class _Job(BaseModel):
    model_config = ConfigDict(extra="allow")

    shortcode: str = Field(pattern=_SHORTCODE)
    title: str
    employment_type: str | None = None
    telecommuting: bool | None = None
    workplace_type: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    locations: list[_Location] = Field(default_factory=list[_Location])
    published_on: str | None = None
    url: str | None = None
    shortlink: str | None = None
    application_url: str | None = None
    description: str | None = None


class _Account(BaseModel):
    model_config = ConfigDict(extra="allow")

    jobs: list[Any]


def parse_account_reference(value: str) -> str:
    """An account slug from a slug, `apply.workable.com/<slug>` or `<slug>.workable.com` link
    (HTTPS only). Only the slug is kept; the link itself is never requested. Raises ValueError."""
    text = value.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE) and (
        "/" in text or text.lower().endswith(".workable.com")
    ):
        text = f"https://{text}"
    if "://" in text:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
        segments = [s for s in parts.path.split("/") if s]
        if parts.scheme.lower() != "https" or parts.username is not None or parts.port is not None:
            raise ValueError(_LINK_ERROR)
        if host == APPLY_HOST and segments:
            text = segments[0]
        elif (
            host.endswith(".workable.com")
            and host.count(".") == 2
            and host not in (APPLY_HOST, "www.workable.com")
        ):
            text = host.split(".")[0]
        else:
            raise ValueError(_LINK_ERROR)
    name = text.lower()
    if not SLUG.match(name):
        raise ValueError("That isn't a valid Workable account name.")
    return name


def _location(job: _Job) -> str | None:
    structured = [
        ", ".join(p for p in (loc.city, loc.region, loc.country) if p) for loc in job.locations
    ]
    parts = [p for p in structured if p] or [
        ", ".join(p for p in (job.city, job.state, job.country) if p)
    ]
    return " · ".join(dict.fromkeys(p for p in parts if p)) or None


def _remote_mode(job: _Job) -> RemoteMode | None:
    mapped = _WORKPLACE.get((job.workplace_type or "").strip().lower().replace("-", "_"))
    if mapped is not None:
        return mapped
    # telecommuting false only means "not flagged remote", never on-site.
    return RemoteMode.REMOTE if job.telecommuting is True else None


def _own_path(path: str, code: str, account: str) -> bool:
    """`/j/<CODE>[/...]` or `/<account>/j/<CODE>[/...]`: the URL must name this job (and, when it
    names an account, this account), so a payload can't claim another job's or account's URL."""
    segments = [s for s in path.split("/") if s]
    if segments and segments[0].lower() == account:
        segments = segments[1:]
    return len(segments) >= 2 and segments[0] == "j" and segments[1].upper() == code


def _apply_url(job: _Job, account: str) -> str | None:
    # Posting page first (what the owner reads), like Ashby; only https on apply.workable.com.
    for candidate in (job.url, job.shortlink, job.application_url):
        if not candidate:
            continue
        parts = urlsplit(candidate.strip())
        try:
            port = parts.port
        except ValueError:
            continue
        if (
            parts.scheme == "https"
            and (parts.hostname or "").lower() == APPLY_HOST
            and port is None
            and parts.username is None
            and _own_path(parts.path, job.shortcode.upper(), account)
        ):
            return candidate.strip()
    return None


def _posted(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.combine(date.fromisoformat(value[:10]), datetime.min.time(), UTC)
    except ValueError:
        return None


def _normalize(raw: dict[str, Any], source: SourceConfig) -> NormalizedOpportunity:
    job = _Job.model_validate(raw)
    code = job.shortcode.upper()
    account = source.identifier.lower()
    url = _apply_url(job, account)
    posted = _posted(job.published_on)
    return NormalizedOpportunity(
        external_id=code,
        identifiers=(
            Identifier(namespace=WORKABLE, value=f"{account}:{code}"),
            *url_identifier(url),
        ),
        title=job.title,
        organization=source.display_name,
        description=html_to_text(job.description),
        opportunity_type=classify_opportunity_type(
            job.title, structured_intern=(job.employment_type or "").lower() == "intern"
        ),
        application_url=url,
        location=_location(job),
        remote_mode=_remote_mode(job),
        posted_at=posted,
        source_published_at=posted,
        raw_payload=raw,
    )


def parse(payload: Any, source: SourceConfig) -> Snapshot:
    account = top_level(_Account, payload, "Workable account")
    return Snapshot(
        items=normalize_each(
            account.jobs, lambda job: _normalize(job, source), lambda job: job.get("shortcode")
        )
    )


def _url(source: SourceConfig) -> str:
    return f"{API}/{quote(source.identifier, safe='')}?details=true"


ADAPTER = Adapter(
    source_type=OpportunitySourceType.ATS, url=_url, parse=parse, normalize=_normalize
)
