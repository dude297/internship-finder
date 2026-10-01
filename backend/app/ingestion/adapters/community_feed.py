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

_DIGITS = re.compile(r"^[0-9]+$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_LEVER_HOSTS = {"jobs.lever.co": "global", "jobs.eu.lever.co": "eu"}


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


def provider_identity(item_id: str, url: str | None) -> Identifier | None:
    """The underlying ATS identity, only for ID formats understood exactly (ADR-008 §6)."""
    kind, _, rest = item_id.partition(":")
    head, _, tail = rest.partition(":")
    head = head.lower()
    if kind == "greenhouse" and SLUG.match(head) and _DIGITS.match(tail):
        return Identifier(namespace=GREENHOUSE, value=f"{head}:{tail}")
    if kind == "lever" and SLUG.match(head) and _UUID.match(tail.lower()):
        # The feed ID doesn't say global vs EU; only the posting URL can, and it must agree.
        parts = urlsplit(url or "")
        region = _LEVER_HOSTS.get((parts.hostname or "").lower())
        segments = [s.lower() for s in parts.path.split("/") if s]
        if parts.scheme == "https" and region and segments[:2] == [head, tail.lower()]:
            return Identifier(namespace=LEVER, value=f"{region}:{head}:{tail.lower()}")
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


ADAPTER = Adapter(source_type=OpportunitySourceType.PUBLIC_FEED, url=_url, parse=parse)
