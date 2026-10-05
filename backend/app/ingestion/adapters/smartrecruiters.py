"""SmartRecruiters public Posting API (ADR-014 §1-§4): unauthenticated GETs of PUBLIC postings on
api.smartrecruiters.com only. Never candidate, application, job-administration, or INTERNAL
destination APIs; never an API key.

Company identifiers are case-insensitive at the provider (verified 2026-10-04: `/companies/
SmartRecruiters/postings` and `/companies/smartrecruiters/postings` return the same postings),
so they're lowercased and stored like the other providers' board names."""

import re
from typing import Any, cast
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict

from app.enums import OpportunitySourceType, RemoteMode, SourceScope
from app.ingestion.adapters import Adapter, CollectRequest, SourceConfig, normalize_each, top_level
from app.ingestion.http import FetchError, fetch_json
from app.ingestion.normalize import (
    SMARTRECRUITERS,
    Identifier,
    ItemError,
    NormalizedOpportunity,
    Snapshot,
    SnapshotError,
    classify_opportunity_type,
    html_to_text,
    is_internship_title,
    parse_timestamp,
    url_identifier,
)

API = "https://api.smartrecruiters.com/v1/companies"
JOBS_HOST = "jobs.smartrecruiters.com"
# Observed identifiers are ASCII letters and digits (e.g. "BoschGroup", "AECOM2", "LLNL"); a
# conservative superset, lowercased. \Z, not $ (no trailing newline).
COMPANY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}\Z")
POSTING_ID = re.compile(r"^[0-9]{1,30}\Z")

PAGE_SIZE = 100  # the documented maximum
MAX_PAGES = 50
MAX_DETAIL_FETCHES = 100
# Only these provider keys are ever stored (ADR-014 §2): never `creator` (a person's name),
# `customField`, or `referralUrl`.
_LIST_KEYS = (
    "id", "name", "uuid", "jobAdId", "refNumber", "company", "releasedDate", "location",
    "typeOfEmployment", "experienceLevel", "department", "function", "industry", "visibility",
    "language",
)  # fmt: skip
_DETAIL_KEYS = (
    "id", "uuid", "name", "company", "jobAd", "postingUrl", "applyUrl", "releasedDate",
    "location", "typeOfEmployment", "experienceLevel", "active", "visibility",
)  # fmt: skip
_SECTIONS = ("companyDescription", "jobDescription", "qualifications", "additionalInformation")


def parse_company_reference(value: str) -> str:
    """A company identifier from an identifier or an official jobs.smartrecruiters.com link
    (only the identifier is kept; the link is never requested). Raises ValueError."""
    text = value.strip()
    if any(ord(c) <= 32 or ord(c) == 127 for c in text):  # urlsplit drops embedded newlines/tabs
        raise ValueError("That isn't a valid SmartRecruiters company identifier.")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE) and "/" in text:
        text = f"https://{text}"
    if "://" in text:
        try:
            parts = urlsplit(text)
            port = parts.port
        except ValueError:
            raise ValueError(
                "Use a SmartRecruiters link like https://jobs.smartrecruiters.com/<company>"
            ) from None
        segments = [s for s in parts.path.split("/") if s]
        # Exact host (no trailing dot, no lookalikes), https only, no credentials or port.
        if (
            parts.scheme.lower() != "https"
            or (parts.hostname or "") != JOBS_HOST
            or not segments
            or "//" in parts.path
            or parts.username is not None
            or parts.password is not None
            or port is not None
        ):
            raise ValueError(
                "Use a SmartRecruiters link like https://jobs.smartrecruiters.com/<company>"
            )
        text = segments[0]
    name = text.lower()
    if not COMPANY.match(name):
        raise ValueError("That isn't a valid SmartRecruiters company identifier.")
    return name


class _Ref(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None


class _Company(BaseModel):
    model_config = ConfigDict(extra="allow")

    identifier: str | None = None


class _Location(BaseModel):
    model_config = ConfigDict(extra="allow")

    city: str | None = None
    region: str | None = None
    country: str | None = None
    remote: bool | None = None
    hybrid: bool | None = None
    fullLocation: str | None = None  # noqa: N815 -- SmartRecruiters' field name


class _Section(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str | None = None
    text: str | None = None


class _Sections(BaseModel):
    model_config = ConfigDict(extra="allow")

    companyDescription: _Section | None = None  # noqa: N815
    jobDescription: _Section | None = None  # noqa: N815
    qualifications: _Section | None = None
    additionalInformation: _Section | None = None  # noqa: N815


class _JobAd(BaseModel):
    model_config = ConfigDict(extra="allow")

    sections: _Sections | None = None


class _Detail(BaseModel):
    model_config = ConfigDict(extra="allow")

    jobAd: _JobAd | None = None  # noqa: N815
    postingUrl: str | None = None  # noqa: N815


class _Posting(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    company: _Company | None = None
    releasedDate: str | None = None  # noqa: N815
    location: _Location | None = None
    typeOfEmployment: _Ref | None = None  # noqa: N815
    experienceLevel: _Ref | None = None  # noqa: N815


class _Entry(BaseModel):
    model_config = ConfigDict(extra="allow")

    posting: _Posting
    detail: _Detail | None = None
    error: dict[str, str] | None = None


class _Payload(BaseModel):
    model_config = ConfigDict(extra="allow")

    postings: list[Any]


class _Page(BaseModel):
    model_config = ConfigDict(extra="allow")

    offset: int
    limit: int
    totalFound: int  # noqa: N815
    content: list[Any]


def _subset(item: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: item[key] for key in keys if key in item}


def _company_matches(item: dict[str, Any], company: str) -> bool:
    ref = item.get("company")
    ident = cast(dict[str, Any], ref).get("identifier") if isinstance(ref, dict) else None
    return isinstance(ident, str) and ident.lower() == company


def _list_page(company: str, offset: int, request: CollectRequest) -> _Page:
    url = (
        f"{API}/{quote(company, safe='')}/postings"
        f"?limit={PAGE_SIZE}&offset={offset}&destination=PUBLIC"
    )
    page = top_level(
        _Page, fetch_json(url, transport=request.transport).data, "SmartRecruiters postings"
    )
    if (
        page.offset != offset
        or page.limit != PAGE_SIZE
        or page.totalFound < 0
        or len(page.content) > PAGE_SIZE
    ):
        raise SnapshotError("schema_mismatch", "SmartRecruiters paged unexpectedly.")
    return page


def _walk(company: str, request: CollectRequest) -> list[Any]:
    """Every list item, or SnapshotError: a partial or shifting walk must never close anything."""
    items: list[Any] = []
    total: int | None = None
    # A provider returning short pages must not turn the walk into thousands of requests.
    requests_left = MAX_PAGES
    while total is None or len(items) < total:
        if requests_left <= 0:
            raise SnapshotError("incomplete_listing", "A listing needed too many requests.")
        requests_left -= 1
        page = _list_page(company, len(items), request)
        if total is None:
            total = page.totalFound
            if -(-total // PAGE_SIZE) > MAX_PAGES:
                raise SnapshotError(
                    "too_many_pages", f"{company} has more than {MAX_PAGES * PAGE_SIZE} postings."
                )
        elif page.totalFound != total:
            raise SnapshotError("inconsistent_listing", "The posting count changed mid-walk.")
        if total and not page.content:
            raise SnapshotError("incomplete_listing", "A listing page ended before the total.")
        items.extend(page.content)
    if len(items) != total:
        raise SnapshotError("inconsistent_listing", "A listing page overran the total.")
    return items


def _fetch_detail(company: str, posting_id: str, request: CollectRequest) -> dict[str, Any]:
    url = f"{API}/{quote(company, safe='')}/postings/{quote(posting_id, safe='')}"
    data = fetch_json(url, transport=request.transport).data
    if not isinstance(data, dict):
        raise LookupError("detail isn't an object")
    detail = cast(dict[str, Any], data)
    if detail.get("id") != posting_id or not _company_matches(detail, company):
        raise LookupError("detail names another posting or company")
    return _subset(detail, _DETAIL_KEYS)


def collect(request: CollectRequest) -> Any:
    company = request.source.identifier
    internships_only = request.scope is SourceScope.INTERNSHIPS_ONLY
    listed = _walk(company, request)
    seen: set[str] = set()
    entries: list[Any] = []
    budget = MAX_DETAIL_FETCHES
    for item in listed:
        if not isinstance(item, dict):
            entries.append(item)  # parse reports it as an invalid item
            continue
        posting = _subset(cast(dict[str, Any], item), _LIST_KEYS)
        entry: dict[str, Any] = {"posting": posting}
        entries.append(entry)
        posting_id, name = posting.get("id"), posting.get("name")
        if isinstance(posting_id, str):
            if posting_id in seen:
                raise SnapshotError("inconsistent_listing", "A posting was listed twice.")
            seen.add(posting_id)
        if (
            not isinstance(posting_id, str)
            or not POSTING_ID.match(posting_id)
            or not isinstance(name, str)
            or posting.get("visibility", "PUBLIC") != "PUBLIC"
            or not _company_matches(posting, company)
            or (internships_only and not is_internship_title(name))
        ):
            continue  # not admitted: no detail request (parse reports or drops it)
        stored = request.known.get(posting_id)
        if isinstance(stored, dict):
            old = cast(dict[str, Any], stored)
            if old.get("posting") == posting and isinstance(old.get("detail"), dict):
                entry["detail"] = old["detail"]
                continue
        if budget <= 0:
            entry["error"] = {
                "code": "detail_deferred",
                "message": "Detail fetch budget reached; retrying next run.",
            }
            continue
        budget -= 1
        try:
            entry["detail"] = _fetch_detail(company, posting_id, request)
        except FetchError as error:
            entry["error"] = {"code": "detail_failed", "message": error.message[:300]}
        except LookupError:
            entry["error"] = {
                "code": "detail_mismatch",
                "message": "The posting detail didn't match its listing.",
            }
    return {"postings": entries}


def _remote_mode(location: _Location | None) -> RemoteMode | None:
    if location is None:
        return None
    if location.remote is True:
        return RemoteMode.REMOTE
    return RemoteMode.HYBRID if location.hybrid is True else None


def _description(detail: _Detail | None) -> str | None:
    sections = detail.jobAd.sections if detail and detail.jobAd else None
    if sections is None:
        return None
    parts: list[str] = []
    for key in _SECTIONS:
        section: _Section | None = getattr(sections, key)
        text = html_to_text(section.text) if section else None
        if section and text:
            title = (section.title or "").strip()
            parts.append(f"{title}\n{text}" if title else text)
    return "\n\n".join(parts) or None


def _normalize(raw: dict[str, Any], source: SourceConfig) -> NormalizedOpportunity:
    entry = _Entry.model_validate(raw)
    posting = entry.posting
    if entry.error:
        raise ItemError(
            entry.error.get("code", "detail_failed"),
            entry.error.get("message", "Detail unavailable."),
            posting.id,
        )
    if not POSTING_ID.match(posting.id):
        raise ItemError("invalid_item", "id: not a SmartRecruiters posting id.")
    ident = posting.company.identifier if posting.company else None
    if (ident or "").lower() != source.identifier:
        raise ItemError("company_mismatch", "Posting belongs to another company.", posting.id)
    posted = parse_timestamp(posting.releasedDate)
    loc = posting.location
    location = (
        (loc.fullLocation or ", ".join(p for p in (loc.city, loc.region, loc.country) if p))
        if loc
        else None
    )
    posting_url = entry.detail.postingUrl if entry.detail else None
    employment, level = posting.typeOfEmployment, posting.experienceLevel
    return NormalizedOpportunity(
        external_id=posting.id,
        identifiers=(
            Identifier(namespace=SMARTRECRUITERS, value=f"{source.identifier}:{posting.id}"),
            *url_identifier(posting_url),
        ),
        title=posting.name,
        organization=source.display_name,
        description=_description(entry.detail),
        opportunity_type=classify_opportunity_type(
            posting.name,
            structured_intern=(employment is not None and employment.id == "intern")
            or (level is not None and level.id == "internship"),
        ),
        application_url=posting_url,
        location=location or None,
        remote_mode=_remote_mode(loc),
        posted_at=posted,
        source_published_at=posted,
        raw_payload=raw,
    )


def parse(payload: Any, source: SourceConfig) -> Snapshot:
    body = top_level(_Payload, payload, "SmartRecruiters postings")

    # Non-PUBLIC postings are excluded before normalization so a complete run closes them.
    def _hidden(entry: Any) -> bool:
        if not isinstance(entry, dict):
            return False
        posting = cast(dict[str, Any], entry).get("posting")
        return (
            isinstance(posting, dict)
            and "visibility" in posting
            and cast(dict[str, Any], posting)["visibility"] != "PUBLIC"
        )

    visible = [entry for entry in body.postings if not _hidden(entry)]

    def _id(entry: dict[str, Any]) -> object:
        posting = entry.get("posting")
        return cast(dict[str, Any], posting).get("id") if isinstance(posting, dict) else None

    return Snapshot(items=normalize_each(visible, lambda e: _normalize(e, source), _id))


def _url(source: SourceConfig) -> str:
    return f"{API}/{source.identifier}/postings"


ADAPTER = Adapter(
    source_type=OpportunitySourceType.ATS,
    url=_url,
    parse=parse,
    normalize=_normalize,
    collect=collect,
)
