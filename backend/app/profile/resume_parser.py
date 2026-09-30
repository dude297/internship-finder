"""Deterministic résumé parser (ADR-011 §2, §7). Pure: bytes in, candidates out, no I/O.

Interface contract; the implementation below is the Milestone 5 scaffold (text only).
"""

from dataclasses import dataclass

from app.enums import FactCategory

PARSER_NAME = "resume-sections"
PARSER_VERSION = "1"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES = 200
TEXT_PLAIN = "text/plain"
APPLICATION_PDF = "application/pdf"


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
    """Sniff, extract text, and find candidates. Raises UnsupportedFileType / UnreadableFile."""
    if b"\x00" in data:
        raise UnsupportedFileType("Only plain-text and PDF files are supported.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UnsupportedFileType("Only plain-text and PDF files are supported.") from None
    if not text.strip():
        raise UnreadableFile("No text found in that file.")
    return ParsedDocument(TEXT_PLAIN, extract_candidates(text))


def extract_candidates(text: str) -> tuple[Candidate, ...]:
    """Scaffold: a `Skills` heading followed by comma-separated lines."""
    found: list[Candidate] = []
    in_skills = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.rstrip(":").casefold() == "skills":
            in_skills = True
        elif not stripped:
            in_skills = False
        elif in_skills:
            found += [
                Candidate(FactCategory.SKILL, name.strip())
                for name in stripped.split(",")
                if name.strip()
            ]
    return tuple(found[:MAX_CANDIDATES])
