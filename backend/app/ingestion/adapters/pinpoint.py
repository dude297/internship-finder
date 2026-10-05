"""Pinpoint public jobs JSON endpoint (ADR-014 §2): one unauthenticated GET of
`https://<company>.pinpointhq.com/postings.json` (documented at developers.pinpointhq.com/docs/
jobs-json-endpoint; the deprecated `jobs.json` is never used). Hosts are per-tenant subdomains of
the provider's own domain, validated as a single DNS label and allowlisted in http.py; customer
custom domains are never fetched.

Closure semantics (ADR-008 §5):
- Not paginated: the response `{"data": [...]}` is the company's whole set of public postings
  (observed 204 postings in one ~600 KB response, 2026-10-05). A successful 200 whose `data` is a
  list is therefore a complete snapshot, and a posting missing from it is closed. An empty list
  is a legitimate complete snapshot (a company with no openings) and closes everything, like the
  other single-request adapters.
- Unknown company: the provider answers 404 (an HTML page) for an unknown subdomain, which the
  fetcher raises as a FetchError, so a typo or a company that left Pinpoint never closes anything.
- A missing/non-list `data` is a schema_mismatch SnapshotError (nothing closes). A bad posting is
  an item error, so the run is partial and nothing closes.
- A posting whose URL is on another company's pinpointhq.com subdomain is a wrong_company
  SnapshotError (nothing imported or closed); http.py also refuses redirects between tenants.
- Request budget: 1 GET per sync; 429/5xx handled by the shared fetcher (retry, then fail).

There is no publication date in the payload, so `posted_at` is never set (first-seen is the
pipeline's job, labelled as such). `deadline_at`, when present, is the only date used; the
calendar date is kept as the provider wrote it, with no timezone conversion."""

import re
from datetime import date, datetime
from typing import Any, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.enums import OpportunitySourceType, RemoteMode
from app.ingestion.adapters import Adapter, SourceConfig, normalize_each, top_level
from app.ingestion.normalize import (
    PINPOINT,
    Identifier,
    NormalizedOpportunity,
    Snapshot,
    SnapshotError,
    classify_opportunity_type,
    html_to_text,
    url_identifier,
)

HOST_SUFFIX = ".pinpointhq.com"
# One lowercase DNS label: never a dot, so `a.b` or `evil.com/x` can't pick another host.
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_WORKPLACE = {"onsite": RemoteMode.ONSITE, "remote": RemoteMode.REMOTE, "hybrid": RemoteMode.HYBRID}


class _Location(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    city: str | None = None


class _Posting(BaseModel):
    model_config = ConfigDict(extra="allow")

    # The posting id (a numeric string today); validated before it becomes an identity.
    id: StrictStr = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    title: str
    url: str | None = None
    description: str | None = None
    key_responsibilities: str | None = None
    skills_knowledge_expertise: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    deadline_at: str | None = None
    location: _Location | None = None


class _Payload(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: list[Any]


def parse_company_reference(value: str) -> str:
    """A company label from a bare label or an `https://<company>.pinpointhq.com/...` link. Only
    the label is kept; the link itself is never requested. Raises ValueError."""
    text = value.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE) and "/" in text:
        text = f"https://{text}"
    if "://" in text:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
        label = host.removesuffix(HOST_SUFFIX)
        # Credentials or a port mean it isn't a plain public link: refuse, don't strip.
        if (
            parts.scheme.lower() != "https"
            or not host.endswith(HOST_SUFFIX)
            or parts.username is not None
            or parts.port is not None
            or not _LABEL.match(label)
        ):
            raise ValueError("Use a Pinpoint link like https://<company>.pinpointhq.com/")
        return label
    name = text.lower()
    if not _LABEL.match(name):
        raise ValueError("That isn't a valid Pinpoint company name.")
    return name


def _deadline(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
    except ValueError:
        return None  # an unreadable deadline is never guessed; the raw payload keeps it


def _own_url(url: str | None, company: str) -> str | None:
    """The posting page, only when it's https on this company's own pinpointhq.com subdomain."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    ok = (
        parts.scheme == "https"
        and (parts.hostname or "") == f"{company}{HOST_SUFFIX}"
        and port is None
        and parts.username is None
        and parts.password is None
    )
    return url.strip() if ok else None


def _description(posting: _Posting) -> str | None:
    sections = [
        html_to_text(html)
        for html in (
            posting.description,
            posting.key_responsibilities,
            posting.skills_knowledge_expertise,
        )
    ]
    return "\n\n".join(s for s in sections if s) or None


def _normalize(raw: dict[str, Any], source: SourceConfig) -> NormalizedOpportunity:
    posting = _Posting.model_validate(raw)
    url = _own_url(posting.url, source.identifier)
    location = posting.location
    return NormalizedOpportunity(
        external_id=posting.id,
        identifiers=(
            Identifier(namespace=PINPOINT, value=f"{source.identifier}:{posting.id}"),
            *url_identifier(url),
        ),
        title=posting.title,
        organization=source.display_name,
        description=_description(posting),
        opportunity_type=classify_opportunity_type(
            posting.title, structured_intern=posting.employment_type == "internship"
        ),
        application_url=url,
        location=(location.name or location.city) if location else None,
        remote_mode=_WORKPLACE.get((posting.workplace_type or "").lower()),
        application_deadline=_deadline(posting.deadline_at),
        raw_payload=raw,
    )


def _check_company(body: _Payload, company: str) -> None:
    """A posting linking to another Pinpoint tenant means the response isn't this company's
    (a renamed or redirected tenant): fail the snapshot so nothing is imported or closed."""
    for raw in body.data:
        url = cast(dict[str, Any], raw).get("url") if isinstance(raw, dict) else None
        if not isinstance(url, str):
            continue
        try:
            host = (urlsplit(url.strip()).hostname or "").lower()
        except ValueError:
            continue
        if host.endswith(HOST_SUFFIX) and host != f"{company}{HOST_SUFFIX}":
            raise SnapshotError("wrong_company", "The response belongs to another company.")


def parse(payload: Any, source: SourceConfig) -> Snapshot:
    body = top_level(_Payload, payload, "Pinpoint postings")
    _check_company(body, source.identifier)
    return Snapshot(
        items=normalize_each(
            body.data,
            lambda posting: _normalize(posting, source),
            lambda posting: posting.get("id"),
        )
    )


def _url(source: SourceConfig) -> str:
    if not _LABEL.match(source.identifier):
        raise ValueError("invalid Pinpoint company")
    return f"https://{source.identifier}{HOST_SUFFIX}/postings.json"


ADAPTER = Adapter(
    source_type=OpportunitySourceType.ATS, url=_url, parse=parse, normalize=_normalize
)
