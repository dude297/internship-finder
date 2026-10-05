"""SmartRecruiters public Posting API (ADR-014 §1-§4): unauthenticated GETs of PUBLIC postings on
api.smartrecruiters.com only. Never candidate, application, job-administration, or INTERNAL
destination APIs; never an API key.

Company identifiers are case-insensitive at the provider (verified 2026-10-04: `/companies/
SmartRecruiters/postings` and `/companies/smartrecruiters/postings` return the same postings),
so they're lowercased and stored like the other providers' board names."""

import re
from typing import Any
from urllib.parse import urlsplit

from app.enums import OpportunitySourceType
from app.ingestion.adapters import Adapter, CollectRequest, SourceConfig
from app.ingestion.normalize import NormalizedOpportunity, Snapshot, SnapshotError

API = "https://api.smartrecruiters.com/v1/companies"
JOBS_HOST = "jobs.smartrecruiters.com"
# Observed identifiers are ASCII letters and digits (e.g. "BoschGroup", "AECOM2", "LLNL"); a
# conservative superset, lowercased. \Z, not $ (no trailing newline).
COMPANY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}\Z")


def parse_company_reference(value: str) -> str:
    """A company identifier from an identifier or an official jobs.smartrecruiters.com link
    (only the identifier is kept; the link is never requested). Raises ValueError."""
    text = value.strip()
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


def _normalize(raw: dict[str, Any], source: SourceConfig) -> NormalizedOpportunity:
    raise NotImplementedError  # Agent A


def parse(payload: Any, source: SourceConfig) -> Snapshot:
    raise SnapshotError("not_implemented", "SmartRecruiters isn't implemented yet.")  # Agent A


def collect(request: CollectRequest) -> Any:
    raise SnapshotError("not_implemented", "SmartRecruiters isn't implemented yet.")  # Agent A


def _url(source: SourceConfig) -> str:
    return f"{API}/{source.identifier}/postings"


ADAPTER = Adapter(
    source_type=OpportunitySourceType.ATS,
    url=_url,
    parse=parse,
    normalize=_normalize,
    collect=collect,
)
