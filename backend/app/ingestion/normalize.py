"""The typed adapter output (ADR-008 §2) and helpers shared by adapters.

Everything an adapter returns is validated here before the pipeline sees it. External content is
untrusted: HTML becomes plain text, URLs must be http(s), and display fields are bounded.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.enums import OpportunityType, RemoteMode

MAX_RAW_PAYLOAD_BYTES = 256 * 1024
MAX_DESCRIPTION_CHARS = 50_000
MAX_IDENTIFIER_CHARS = 1024

# Identifier namespaces (ADR-008 §6).
ZSHAH = "zshah"
GREENHOUSE = "greenhouse"
LEVER = "lever"
URL = "url"

# Board tokens and site slugs as they appear in provider URLs. Lowercased on both sides.
SLUG = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class ItemError(Exception):
    """One item can't be used. The pipeline records it and moves on."""

    def __init__(self, code: str, message: str, external_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.external_id = external_id


class SnapshotError(Exception):
    """The response as a whole is unusable (wrong shape, incomplete): the run fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _truncate(limit: int) -> AfterValidator:
    return AfterValidator(lambda value: value if len(value) <= limit else value[: limit - 1] + "…")


def _http_url(value: str | None) -> str | None:
    """Only absolute http(s) URLs without credentials; anything else is dropped (the raw payload
    still has it)."""
    if value is None or len(value) > 2048:
        return None
    try:
        parts = urlsplit(value.strip())
        parts.port  # noqa: B018 -- raises ValueError for an invalid port
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    if parts.username or parts.password or re.search(r"\s", value.strip()):
        return None
    return value.strip()


class Identifier(BaseModel):
    model_config = ConfigDict(frozen=True)

    namespace: str = Field(max_length=32)
    value: str = Field(min_length=1, max_length=MAX_IDENTIFIER_CHARS)


class NormalizedOpportunity(BaseModel):
    """One source item in the shape every source shares. Adapters produce it; only the pipeline
    persists it. Text fields are bounded to the canonical column sizes (long values are
    truncated; the raw payload keeps the original)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    external_id: str = Field(min_length=1, max_length=255)
    identifiers: tuple[Identifier, ...] = ()
    title: Annotated[str, Field(min_length=1), _truncate(300)]
    organization: Annotated[str, Field(min_length=1), _truncate(200)]
    description: Annotated[str, _truncate(MAX_DESCRIPTION_CHARS)] | None = None
    opportunity_type: OpportunityType = OpportunityType.OTHER
    application_url: Annotated[str | None, AfterValidator(_http_url)] = None
    location: Annotated[str, _truncate(200)] | None = None
    remote_mode: RemoteMode | None = None
    posted_at: datetime | None = None
    source_published_at: datetime | None = None
    source_updated_at: datetime | None = None
    raw_payload: dict[str, Any]

    @field_validator("title", "organization", "location", mode="before")
    @classmethod
    def _one_line(cls, value: object) -> object:
        return (" ".join(value.split()) or None) if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def _stripped(cls, value: object) -> object:
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("posted_at", "source_published_at", "source_updated_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value

    @field_validator("raw_payload")
    @classmethod
    def _bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(canonical_json(value)) > MAX_RAW_PAYLOAD_BYTES:
            raise ValueError("raw item is larger than 256 KB")
        return value

    def content_hash(self) -> str:
        """Change detector for the whole item (raw payload included); not a security control."""
        return hashlib.sha256(canonical_json(self.model_dump(mode="json")).encode()).hexdigest()


@dataclass
class Snapshot:
    """A validated source response: its items (or per-item errors) in source order."""

    items: list[NormalizedOpportunity | ItemError] = field(
        default_factory=list[NormalizedOpportunity | ItemError]
    )
    generated_at: datetime | None = None


def canonical_json(value: Any) -> str:
    """Deterministic serialization: sorted keys, no whitespace, non-ASCII kept."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def parse_timestamp(value: object) -> datetime | None:
    """ISO 8601 strings with a timezone (or `Z`), or epoch milliseconds. Anything else → None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value / 1000, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def canonical_url(value: str | None) -> str | None:
    """Exact job-URL identity: lowercase scheme and host, no default port, no fragment; path and
    query unchanged. A URL without a path or query (a careers home page) isn't an identity."""
    url = _http_url(value)
    if url is None:
        return None
    parts = urlsplit(url)
    if parts.path in ("", "/") and not parts.query:
        return None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    default_port = {"http": 80, "https": 443}[scheme]
    netloc = host if parts.port in (None, default_port) else f"{host}:{parts.port}"
    result = urlunsplit((scheme, netloc, parts.path, parts.query, ""))
    return result if len(result) <= MAX_IDENTIFIER_CHARS else None


def url_identifier(value: str | None) -> tuple[Identifier, ...]:
    url = canonical_url(value)
    return (Identifier(namespace=URL, value=url),) if url else ()


# --- HTML to plain text -------------------------------------------------------------------------

_BLOCK_TAGS = frozenset(
    [
        "p",
        "div",
        "br",
        "li",
        "ul",
        "ol",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "tr",
        "table",
        "section",
        "article",
        "header",
        "footer",
        "blockquote",
        "pre",
    ]
)
_SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "head"})


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self.skipping += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
            if tag == "li":
                self.parts.append("• ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self.skipping = max(self.skipping - 1, 0)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skipping:
            self.parts.append(data)


def html_to_text(html: str | None, *, entity_escaped: bool = False) -> str | None:
    """Untrusted HTML → plain text. Tags are dropped (scripts and styles with their content),
    entities decoded, whitespace tidied. `entity_escaped` first decodes HTML that the source
    delivers as escaped text (Greenhouse `content`). The result is only ever shown as text."""
    if not html:
        return None
    parser = _TextExtractor()
    parser.feed(unescape(html) if entity_escaped else html)
    parser.close()
    lines: list[str] = []
    for raw_line in "".join(parser.parts).splitlines():
        line = " ".join(raw_line.split())
        if lines and lines[-1] == "•" and line:  # "<li><p>text</p></li>": keep the bullet inline
            lines[-1] = f"• {line}"
        else:
            lines.append(line)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text or None
