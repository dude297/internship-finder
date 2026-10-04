"""The built-in broad discovery feed: zshah101's public internship JSON API (MIT repository; we
use the published API only and copy none of its code). See docs/sources.md.

The feed is discovery metadata, not eligibility evidence: its sponsorship, H-1B, skills, and
category fields stay in the raw payload and never become requirements (ADR-008 §9).
"""

import re
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from app.enums import OpportunitySourceType, RemoteMode
from app.ingestion.adapters import Adapter, SourceConfig, normalize_each, top_level
from app.ingestion.normalize import (
    ASHBY,
    GREENHOUSE,
    LEVER,
    SLUG,
    ZSHAH,
    Identifier,
    NormalizedOpportunity,
    Snapshot,
    SnapshotError,
    classify_opportunity_type,
    parse_timestamp,
    url_identifier,
)

# Built-in feeds by registry identifier. The endpoint is fixed here, never configurable.
FEEDS = {
    "zshah-tech-internships": (
        "https://zshah101.github.io/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships"
        "/api/jobs.json"
    ),
}
BUILTIN_IDENTIFIER = "zshah-tech-internships"

_DIGITS = re.compile(r"^[0-9]+\Z")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_LEVER_HOSTS = {"jobs.lever.co": "global", "jobs.eu.lever.co": "eu"}
_ASHBY_HOSTS = {"jobs.ashbyhq.com": "global"}
_GREENHOUSE_HOSTS = {
    "boards.greenhouse.io": "global",
    "job-boards.greenhouse.io": "global",
    "boards.eu.greenhouse.io": "eu",
    "job-boards.eu.greenhouse.io": "eu",
}


class _Item(BaseModel):
    """The fields we map. Everything else is kept only in the raw payload."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=255)
    company: str
    title: str
    url: str | None = None
    location: str | None = None
    posted_at: str | None = None
    remote: bool | None = None
    program: str | None = None


class _Feed(BaseModel):
    jobs: list[Any]
    count: int | None = None
    generated_at: str | None = None


def _hosted_path(url: str | None, hosts: dict[str, str]) -> tuple[str, list[str]] | None:
    """(region, lowercased path segments) for a plain https link on one of `hosts`. Credentials
    or an explicit port mean it isn't a plain public posting link: no identity (ADR-013 §2)."""
    try:
        parts = urlsplit(url or "")
        port = parts.port
    except ValueError:
        return None
    region = hosts.get((parts.hostname or "").lower())
    if parts.scheme != "https" or region is None or parts.username is not None or port is not None:
        return None
    return region, [s.lower() for s in parts.path.split("/") if s]


def provider_identity(item_id: str, url: str | None) -> Identifier | None:
    """The underlying ATS identity, only for ID formats understood exactly (ADR-008 §6,
    ADR-013 §2). A posting link on the provider's own host must agree with the ID."""
    kind, _, rest = item_id.partition(":")
    head, _, tail = rest.partition(":")
    head = head.lower()
    if kind == "greenhouse" and SLUG.match(head) and _DIGITS.match(tail):
        # The ID alone is the identity (many feed links are company career pages), but a link on
        # a Greenhouse board host naming a different board is conflicting evidence.
        hosted = _hosted_path(url, _GREENHOUSE_HOSTS)
        if hosted is not None and hosted[1][:1] != [head]:
            return None
        return Identifier(namespace=GREENHOUSE, value=f"{head}:{tail}")
    if kind == "lever" and SLUG.match(head) and _UUID.match(tail.lower()):
        # The feed ID doesn't say global vs EU; only the posting URL can, and it must agree.
        hosted = _hosted_path(url, _LEVER_HOSTS)
        if hosted is not None and hosted[1][:2] == [head, tail.lower()]:
            return Identifier(namespace=LEVER, value=f"{hosted[0]}:{head}:{tail.lower()}")
    if kind == "ashby" and SLUG.match(head) and _UUID.match(tail.lower()):
        # Both the provider-shaped ID and a matching hosted posting link (ADR-013 §2).
        hosted = _hosted_path(url, _ASHBY_HOSTS)
        if hosted is not None and hosted[1][:2] == [head, tail.lower()]:
            return Identifier(namespace=ASHBY, value=f"{head}:{tail.lower()}")
    return None


def _normalize(raw: dict[str, Any]) -> NormalizedOpportunity:
    item = _Item.model_validate(raw)
    posted = parse_timestamp(item.posted_at)
    identifiers = [Identifier(namespace=ZSHAH, value=item.id)]
    provider = provider_identity(item.id, item.url)
    if provider:
        identifiers.append(provider)
    identifiers.extend(url_identifier(item.url))
    return NormalizedOpportunity(
        external_id=item.id,
        identifiers=tuple(identifiers),
        title=item.title,
        organization=item.company,
        opportunity_type=classify_opportunity_type(
            item.title, structured_intern=item.program == "Internship"
        ),
        application_url=item.url,
        location=item.location,
        # `remote: false` doesn't say on-site; only `true` is unambiguous.
        remote_mode=RemoteMode.REMOTE if item.remote is True else None,
        posted_at=posted,
        source_published_at=posted,
        raw_payload=raw,
    )


def parse(payload: Any, _source: SourceConfig) -> Snapshot:
    feed = top_level(_Feed, payload, "feed")
    if feed.count is not None and feed.count != len(feed.jobs):
        raise SnapshotError(
            "incomplete_snapshot",
            f"The feed declared {feed.count} jobs but contained {len(feed.jobs)}.",
        )
    return Snapshot(
        items=normalize_each(feed.jobs, _normalize, lambda item: item.get("id")),
        generated_at=parse_timestamp(feed.generated_at),
    )


def _url(source: SourceConfig) -> str:
    try:
        return FEEDS[source.identifier]
    except KeyError:
        raise SnapshotError("unknown_feed", "Unknown built-in feed.") from None


ADAPTER = Adapter(
    source_type=OpportunitySourceType.PUBLIC_FEED,
    url=_url,
    parse=parse,
    normalize=lambda raw, _source: _normalize(raw),
)
