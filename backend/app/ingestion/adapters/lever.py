"""Lever Postings API: public published postings on api.lever.co (global) and api.eu.lever.co
(EU). Never the authenticated Data API; candidates are never submitted."""

import re
from html import escape
from typing import Any
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, RootModel

from app.enums import OpportunitySourceType, RemoteMode, SourceRegion
from app.ingestion.adapters import Adapter, SourceConfig, normalize_each, top_level
from app.ingestion.normalize import (
    LEVER,
    SLUG,
    Identifier,
    NormalizedOpportunity,
    Snapshot,
    classify_opportunity_type,
    html_to_text,
    parse_timestamp,
    url_identifier,
)

API = {
    SourceRegion.GLOBAL: "https://api.lever.co/v0/postings",
    SourceRegion.EU: "https://api.eu.lever.co/v0/postings",
}
# Public job-site hosts and the API region each belongs to.
SITE_HOSTS = {"jobs.lever.co": SourceRegion.GLOBAL, "jobs.eu.lever.co": SourceRegion.EU}
_WORKPLACE = {"onsite": RemoteMode.ONSITE, "remote": RemoteMode.REMOTE, "hybrid": RemoteMode.HYBRID}


class _Categories(BaseModel):
    model_config = ConfigDict(extra="allow")

    commitment: str | None = None
    location: str | None = None
    allLocations: list[str] | None = None  # noqa: N815 -- Lever's field name


class _ListSection(BaseModel):
    text: str = ""
    content: str = ""


class _Posting(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=255)
    text: str
    hostedUrl: str | None = None  # noqa: N815
    categories: _Categories | None = None
    workplaceType: str | None = None  # noqa: N815
    createdAt: int | None = None  # noqa: N815
    description: str | None = None
    lists: list[_ListSection] = Field(default_factory=list[_ListSection])
    additional: str | None = None


class _Postings(RootModel[list[Any]]):
    pass


def parse_site_reference(value: str, region: SourceRegion | None) -> tuple[str, SourceRegion]:
    """A site slug and region from a slug (+ region, default global) or a public job-site URL
    (jobs.lever.co / jobs.eu.lever.co, which decides the region). Raises ValueError."""
    text = value.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE) and "/" in text:
        text = f"https://{text}"
    if "://" in text:
        parts = urlsplit(text)
        segments = [s for s in parts.path.split("/") if s]
        url_region = SITE_HOSTS.get((parts.hostname or "").lower())
        # Credentials or a port mean it isn't a plain public job-site link: refuse, don't strip.
        if (
            url_region is None
            or not segments
            or parts.username is not None
            or parts.port is not None
        ):
            raise ValueError("Use a Lever job-site link like https://jobs.lever.co/<site>")
        if region is not None and region is not url_region:
            raise ValueError("The link's region doesn't match the selected region.")
        text, region = segments[0], url_region
    site = text.lower()
    if not SLUG.match(site):
        raise ValueError("That isn't a valid Lever site name.")
    return site, region or SourceRegion.GLOBAL


def _description(posting: _Posting) -> str | None:
    html = posting.description or ""
    for section in posting.lists:
        html += f"<h3>{escape(section.text)}</h3><ul>{section.content}</ul>"
    html += posting.additional or ""
    return html_to_text(html)


def _normalize(raw: dict[str, Any], source: SourceConfig) -> NormalizedOpportunity:
    posting = _Posting.model_validate(raw)
    categories = posting.categories or _Categories()
    commitment = (categories.commitment or "").lower()
    locations = categories.allLocations or ([categories.location] if categories.location else [])
    region = source.region or SourceRegion.GLOBAL
    created = parse_timestamp(posting.createdAt)
    return NormalizedOpportunity(
        external_id=posting.id,
        identifiers=(
            Identifier(
                namespace=LEVER, value=f"{region.value}:{source.identifier}:{posting.id.lower()}"
            ),
            *url_identifier(posting.hostedUrl),
        ),
        title=posting.text,
        organization=source.display_name,
        description=_description(posting),
        # A structured commitment field, not prose: "Intern" / "Internship".
        opportunity_type=classify_opportunity_type(
            posting.text, structured_intern="intern" in commitment
        ),
        application_url=posting.hostedUrl,
        location=" · ".join(locations) or None,
        remote_mode=_WORKPLACE.get((posting.workplaceType or "").lower()),
        posted_at=created,
        source_published_at=created,
        raw_payload=raw,
    )


def parse(payload: Any, source: SourceConfig) -> Snapshot:
    postings = top_level(_Postings, payload, "Lever postings").root
    return Snapshot(
        items=normalize_each(
            postings, lambda item: _normalize(item, source), lambda item: item.get("id")
        )
    )


def _url(source: SourceConfig) -> str:
    base = API[source.region or SourceRegion.GLOBAL]
    return f"{base}/{quote(source.identifier, safe='')}?mode=json"


ADAPTER = Adapter(source_type=OpportunitySourceType.ATS, url=_url, parse=parse)
