"""Deterministic résumé parser (ADR-011 §2, §6, §7). Pure: bytes in, candidates out, no I/O.

Same bytes, same version -> same output, in the same order (ADR-011 §7). No AI, no OCR, no
network calls, no randomness, no wall-clock reads.
"""

import io
import logging
import re
from dataclasses import dataclass

from pypdf import PdfReader

from app.enums import FactCategory

PARSER_NAME = "resume-sections"
PARSER_VERSION = "1"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES = 200
TEXT_PLAIN = "text/plain"
APPLICATION_PDF = "application/pdf"

# ADR-011 §2: extraction stops at 100,000 characters, for text and PDF alike.
_MAX_TEXT_CHARS = 100_000
# ADR-011 §2: only the first 20 pages of a PDF are read.
_MAX_PDF_PAGES = 20

# pypdf logs warnings (e.g. malformed content streams) through the "pypdf" logger. Nothing we
# extract from a file may reach a log, so this is raised once, at import time, rather than
# threaded through every call site.
logging.getLogger("pypdf").setLevel(logging.ERROR)


class UnsupportedFileType(Exception):
    """Not plain UTF-8 text or a PDF (HTTP 415). The message is safe to show."""


class UnreadableFile(Exception):
    """A supported type that can't be read, or has no text (HTTP 422). The message is safe to
    show: it never contains file content."""


@dataclass(frozen=True)
class Candidate:
    category: FactCategory
    name: str
    description: str | None = None


@dataclass(frozen=True)
class ParsedDocument:
    content_type: str  # TEXT_PLAIN or APPLICATION_PDF
    candidates: tuple[Candidate, ...]


def parse_document(data: bytes) -> ParsedDocument:
    """Sniff, extract text, and find candidates.

    Raises UnsupportedFileType / UnreadableFile. The API already enforces MAX_UPLOAD_BYTES via
    Content-Length and a bounded read (ADR-011 §2); this is a defensive ValueError, not a
    user-facing outcome, because reaching it means that check was bypassed.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("data exceeds MAX_UPLOAD_BYTES")

    if data.startswith(b"%PDF-"):
        return ParsedDocument(APPLICATION_PDF, extract_candidates(_extract_pdf_text(data)))

    if b"\x00" in data:
        raise UnsupportedFileType("Only plain-text (.txt) and text-based PDF files are supported.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UnsupportedFileType(
            "Only plain-text (.txt) and text-based PDF files are supported."
        ) from None

    text = text[:_MAX_TEXT_CHARS]
    if not text.strip():
        raise UnreadableFile("No text found in that file.")
    return ParsedDocument(TEXT_PLAIN, extract_candidates(text))


def _extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise UnreadableFile("Password-protected PDFs aren't supported.")
        chunks: list[str] = []
        total = 0
        for index, page in enumerate(reader.pages):
            if index >= _MAX_PDF_PAGES:
                break
            page_text = page.extract_text() or ""
            chunks.append(page_text)
            total += len(page_text)
            if total >= _MAX_TEXT_CHARS:
                break
        text = "".join(chunks)[:_MAX_TEXT_CHARS]
    except UnreadableFile:
        raise
    except Exception:
        raise UnreadableFile("Couldn't read that PDF.") from None

    if not text.strip():
        raise UnreadableFile("No text found in that PDF. Scanned PDFs aren't supported.")
    return text


# --- Section detection (ADR-011 §7) -----------------------------------------------------------

_BULLET_CHARS = ("-", "*", "•", "◦", "▪", "–")  # - * • ◦ ▪ –
_LIST_SPLIT_RE = re.compile(r"[,;|•·]")  # , ; | • ·
_WHITESPACE_RE = re.compile(r"\s+")

_LIST_CATEGORIES = frozenset({FactCategory.SKILL, FactCategory.COURSE})
_LIST_ITEM_CAP = {FactCategory.SKILL: 100, FactCategory.COURSE: 150}
_ENTRY_NAME_CAP = 150
_ENTRY_DESCRIPTION_CAP = 2_000
_LABEL_PREFIX_MAX_LEN = 30
_UNKNOWN_HEADING_MAX_LEN = 40

# Deliberately a fixed deny-list, not a generic Title-Case/ALL-CAPS heuristic: an entry's own
# name (e.g. "Synthetic Robot Arm", "Example Corp") is just as often short and Title Case, so a
# generic heuristic would end the section on the entry that should start it. These are headings
# that never introduce content we extract, so seeing one always ends the current section.
_STOP_HEADING_TEXTS = (
    "contact",
    "contact information",
    "personal information",
    "summary",
    "professional summary",
    "summary of qualifications",
    "objective",
    "career objective",
    "objective statement",
    "profile",
    "about",
    "about me",
    "references",
)


def _normalize_heading(line: str) -> str:
    s = line.strip().lstrip("#").strip()
    if s.startswith(_BULLET_CHARS):
        s = s[1:].strip()
    if s.endswith(":"):
        s = s[:-1].strip()
    s = _WHITESPACE_RE.sub(" ", s).replace("&", "and")
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s.casefold()


_RAW_ALIASES: dict[FactCategory, tuple[str, ...]] = {
    FactCategory.SKILL: (
        "skills",
        "technical skills",
        "technologies",
        "skills & technologies",
        "technical skills & tools",
        "tools",
        "programming languages",
        "languages & tools",
    ),
    FactCategory.COURSE: ("coursework", "relevant coursework", "courses", "relevant courses"),
    FactCategory.PROJECT: (
        "projects",
        "personal projects",
        "selected projects",
        "academic projects",
    ),
    FactCategory.RESEARCH: ("research", "research experience"),
    FactCategory.EXPERIENCE: (
        "experience",
        "work experience",
        "employment",
        "professional experience",
    ),
    FactCategory.ACTIVITY: (
        "activities",
        "leadership",
        "activities & leadership",
        "leadership & activities",
        "extracurricular activities",
        "extracurriculars",
        "volunteering",
        "volunteer experience",
    ),
    FactCategory.AWARD: (
        "awards",
        "honors",
        "honors & awards",
        "awards & honors",
        "achievements",
    ),
    FactCategory.EDUCATION: ("education",),
}

_ALIASES: dict[str, FactCategory] = {
    _normalize_heading(alias): category
    for category, aliases in _RAW_ALIASES.items()
    for alias in aliases
}

_STOP_HEADINGS = frozenset(_normalize_heading(h) for h in _STOP_HEADING_TEXTS)


def _is_bullet_line(line: str) -> bool:
    return line.startswith(_BULLET_CHARS)


def _looks_like_unknown_heading(line: str) -> bool:
    """A short, non-bulleted, non-sentence line matching a known non-content heading (Contact,
    Summary, Objective, References, ...): it ends whatever entry section came before it."""
    if len(line) > _UNKNOWN_HEADING_MAX_LEN or line.endswith(".") or _is_bullet_line(line):
        return False
    return _normalize_heading(line) in _STOP_HEADINGS


def _strip_bullet(line: str) -> str:
    if line.startswith(_BULLET_CHARS):
        return line[1:].strip()
    return line


def _strip_label(line: str) -> str:
    label, sep, rest = line.partition(":")
    if sep and len(label.strip()) <= _LABEL_PREFIX_MAX_LEN:
        return rest.strip()
    return line


def _truncate(value: str, limit: int) -> str:
    """Deterministic truncation at the last word boundary within `limit`, falling back to a hard
    cut when there's no earlier space (e.g. one very long word)."""
    if len(value) <= limit:
        return value
    cut = value[:limit]
    last_space = cut.rfind(" ")
    return cut[:last_space].rstrip() if last_space > 0 else cut.rstrip()


def _split_list_items(line: str, category: FactCategory) -> list[Candidate]:
    cleaned = _strip_label(_strip_bullet(line))
    cap = _LIST_ITEM_CAP[category]
    items: list[Candidate] = []
    for raw_item in _LIST_SPLIT_RE.split(cleaned):
        item = raw_item.strip()
        if item and len(item) <= cap:
            items.append(Candidate(category, item))
    return items


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    seen: set[tuple[FactCategory, str]] = set()
    result: list[Candidate] = []
    for candidate in candidates:
        key = (candidate.category, candidate.name.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def extract_candidates(text: str) -> tuple[Candidate, ...]:
    """Find section headings by the fixed alias table (ADR-011 §7) and turn skill/course
    sections into lists and the rest into name+description entries. Text outside a known
    section is ignored, so contact details at the top of a résumé are never extracted."""
    candidates: list[Candidate] = []
    category: FactCategory | None = None
    entry_name: str | None = None
    entry_description: list[str] = []

    def flush_entry() -> None:
        nonlocal entry_name, entry_description
        if entry_name is not None and category is not None:
            description = " ".join(entry_description) if entry_description else None
            candidates.append(
                Candidate(
                    category,
                    _truncate(entry_name, _ENTRY_NAME_CAP),
                    _truncate(description, _ENTRY_DESCRIPTION_CAP) if description else None,
                )
            )
        entry_name = None
        entry_description = []

    for raw_line in text.splitlines():
        stripped = raw_line.strip()

        if not stripped:
            if category is not None and category not in _LIST_CATEGORIES:
                flush_entry()
            continue

        heading = _ALIASES.get(_normalize_heading(stripped))
        if heading is not None:
            if category is not None and category not in _LIST_CATEGORIES:
                flush_entry()
            category = heading
            continue

        if category is None:
            continue  # text outside any known section is ignored

        if category in _LIST_CATEGORIES:
            candidates.extend(_split_list_items(stripped, category))
            continue

        if _looks_like_unknown_heading(stripped):
            flush_entry()
            category = None
            continue

        if _is_bullet_line(stripped):
            if entry_name is not None:
                entry_description.append(_strip_bullet(stripped))
            continue

        flush_entry()
        entry_name = stripped

    if category is not None and category not in _LIST_CATEGORIES:
        flush_entry()

    return tuple(_dedupe(candidates)[:MAX_CANDIDATES])
