"""Deterministic requirement extraction, `requirements-rules` v1 (ADR-012 §5).

Pure: no network, no AI, no clock, no randomness. Same input always yields the same output.
Precision over recall: a sentence is only turned into a proposal when it explicitly states a
hard requirement in one of the forms below; anything hedged, negated, conditional on a range,
listed with alternatives, or otherwise ambiguous is left alone.
"""

import re
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.enums import EducationLevel, RequirementAppliesAt, RequirementType
from app.opportunities.eligibility.schemas import REQUIREMENT_VALUE_SCHEMAS
from app.opportunities.requirements.identity import ExtractionInput, semantic_key

EXTRACTOR_NAME = "requirements-rules"
EXTRACTOR_VERSION = "1"

MAX_PROPOSALS = 20
MAX_EXCERPT_CHARS = 300
MIN_PLAUSIBLE_AGE = 10
MAX_PLAUSIBLE_AGE = 30

WORK_AUTH_LABEL = "Authorized to work in the United States"
OTHER_SECURITY_CLEARANCE_LABEL = "Security clearance required"


class Proposal(BaseModel):
    """One extracted requirement proposal. Immutable; identity is `semantic_key`, never the
    source text or position."""

    model_config = ConfigDict(frozen=True)

    requirement_type: RequirementType
    value: dict[str, Any]
    applies_at: RequirementAppliesAt = RequirementAppliesAt.PROGRAM_START
    reference_date: date | None = None
    source_text: str


# --- sentence splitting -------------------------------------------------------------------------
# Sentences end at . ! ? and also at line breaks and bullets: descriptions arrive as plain text
# where each <li> is its own line without a period, and one bullet list must not become one
# "sentence" (one hedge word in it would silence every bullet, and only one proposal per sentence
# is made). "U.S." is protected so "Must be a U.S. citizen." stays one sentence.

_US_PLACEHOLDER = ""  # a Unicode private-use codepoint: won't collide with real text
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\s*[\r\n]+\s*|\s*[•▪◦]\s*")


def _protect_abbreviations(text: str) -> str:
    return re.sub(r"\bU\.S\.", f"U{_US_PLACEHOLDER}S{_US_PLACEHOLDER}", text, flags=re.IGNORECASE)


def _restore_abbreviations(text: str) -> str:
    return text.replace(_US_PLACEHOLDER, ".")


def _sentences(text: str | None) -> list[str]:
    if not text:
        return []
    protected = _protect_abbreviations(text)
    return [
        _restore_abbreviations(fragment).strip()
        for fragment in _SENTENCE_BOUNDARY.split(protected)
        if fragment.strip()
    ]


# --- sentence-level filters -----------------------------------------------------------------------
# Any of these anywhere in a sentence means it's never a hard requirement (ADR-012 §5): hedges and
# preferences, and negations ("No security clearance is required", "must not be enrolled",
# "non-U.S. citizens", "are not eligible") or upper bounds ("18 or younger") that would invert
# the meaning of an otherwise matching phrase.

_HEDGE_RE = re.compile(
    r"\b(?:preferred|nice to have|bonus|ideally|ideal|typically|most|usually|encouraged|"
    r"welcome)\b|\bplus\b",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(
    r"\b(?:not|no|never|cannot|can't|don't|doesn't|isn't|aren't|won't|nor|neither|"
    r"ineligible)\b|\bnon[-\s]|\bor (?:younger|under|less)\b|\bunder the age\b|\bunder \d",
    re.IGNORECASE,
)


def _skipped(sentence: str) -> bool:
    return bool(_HEDGE_RE.search(sentence) or _NEGATION_RE.search(sentence))


Match = tuple[dict[str, Any], int]  # (value, position of the matched phrase in the sentence)


# --- minimum_age ----------------------------------------------------------------------------------
# The number must be an age: followed by "years" or ending the clause. "at least 18 months into
# the degree", "at least 20 hours per week", and "at least 16 weeks" are never ages.

# Or a date phrase follows: "at least 18 at the time of application", "at least 16 by June 1".
_AGE_END = r"(?:\s+years?\b|(?=\s*(?:[.,;:)]|$|(?:at|by|on|as of|when|before)\b)))"
_AGE_PATTERNS = (
    re.compile(r"\bmust be at least (\d{1,3})" + _AGE_END, re.IGNORECASE),
    re.compile(r"\bminimum age(?: of| is|:)?\s+(\d{1,3})" + _AGE_END, re.IGNORECASE),
    re.compile(r"\bmust be (\d{1,3}) years (?:of age|old) or older\b", re.IGNORECASE),
    re.compile(r"\bapplicants must be (?:at least )?(\d{1,3}) years of age\b", re.IGNORECASE),
)


def _match_minimum_age(sentence: str) -> Match | None:
    for pattern in _AGE_PATTERNS:
        match = pattern.search(sentence)
        if match is None:
            continue
        years = int(match.group(1))
        if MIN_PLAUSIBLE_AGE <= years <= MAX_PLAUSIBLE_AGE:
            return {"years": years}, match.start()
        return None  # out-of-range age: the sentence is about age, but not a usable proposal
    return None


# --- education --------------------------------------------------------------------------------
# Mandatory enrollment language only; "senior", "teens", "young people" etc. never match because
# they aren't accepted lead-ins or level words. A sentence naming more than one level ("a high
# school student, undergraduate, or graduate student") is a list of alternatives that one level
# would misrepresent: skipped.

_EDU_LEVELS = {
    "high school": EducationLevel.HIGH_SCHOOL,
    "undergraduate": EducationLevel.UNDERGRADUATE,
    "graduate": EducationLevel.GRADUATE,
}
_LEVEL_WORD_RE = re.compile(r"\b(high school|undergraduate|graduate)\b", re.IGNORECASE)

_EDU_RE = re.compile(
    r"\b(?:must be (?:an? )?|currently enrolled (?:in )?(?:an? )?|must be enrolled in an? )"
    r"(?P<incoming>incoming |rising |entering )?"
    r"(?P<level>high school|undergraduate|graduate)"
    # The level must name enrollment: "... student(s)" / "... program", or end the clause
    # ("currently enrolled in high school."). "a graduate of", "a high school graduate", and
    # "a high school diploma" describe a finished level, never current enrollment.
    r"(?:\s+(?:students?|programs?)\b|(?=\s*(?:[.,;:]|only\b|$)))",
    re.IGNORECASE,
)

# A bare "incoming/rising/entering LEVEL student(s)" is itself an explicit, mandatory enrollment
# statement even without a leading "must be" / "currently enrolled".
_EDU_INCOMING_RE = re.compile(
    r"\b(?P<incoming>incoming|rising|entering)\s+(?P<level>high school|undergraduate|graduate)"
    r"\s+students?\b",
    re.IGNORECASE,
)


def _match_education(sentence: str) -> Match | None:
    if len({word.lower() for word in _LEVEL_WORD_RE.findall(sentence)}) > 1:
        return None
    match = _EDU_RE.search(sentence) or _EDU_INCOMING_RE.search(sentence)
    if match is None:
        return None
    level = _EDU_LEVELS[match.group("level").lower()]
    return {"levels": [level.value], "accepts_incoming": bool(match.group("incoming"))}, (
        match.start()
    )


# --- citizenship ------------------------------------------------------------------------------
# Only "U.S." has a mapping in v1 (ADR-012 §5: "a small explicit table"). Any sentence that also
# names another status ("or permanent resident", "U.S. national", "DACA recipient", a visa) is a
# broader requirement than citizenship: never reduced to it. "U.S. person" never matches.

_CITIZENSHIP_RE = re.compile(
    r"\bmust be an? (?:U\.S\.|united states) citizen\b"
    r"|\b(?:U\.S\.|united states) citizens? only\b"
    r"|\b(?:U\.S\.|united states) citizenship(?: is)? required\b",
    re.IGNORECASE,
)
_OTHER_STATUS_RE = re.compile(
    r"\b(?:permanent residents?|green card|residents?|nationals?|refugees?|asylees?|visas?|"
    r"daca|tps|lawful)\b",
    re.IGNORECASE,
)


def _match_citizenship(sentence: str) -> Match | None:
    if _OTHER_STATUS_RE.search(sentence):
        return None
    match = _CITIZENSHIP_RE.search(sentence)
    return ({"countries": ["US"]}, match.start()) if match else None


# --- work_authorization -------------------------------------------------------------------------

_WORK_AUTH_RE = re.compile(
    r"\bauthorized to work in the (?:united states|U\.S\.)"
    r"|\bwork authorization(?: is)? required\b"
    r"|\bcitizens? or (?:lawful )?permanent residents?\b"
    r"|\bcitizens? or green card holders?\b",
    re.IGNORECASE,
)


def _match_work_authorization(sentence: str) -> Match | None:
    match = _WORK_AUTH_RE.search(sentence)
    return ({"description": WORK_AUTH_LABEL}, match.start()) if match else None


# --- other --------------------------------------------------------------------------------------
# Used sparingly (ADR-012 §5): only hard requirements no evaluator rule covers, and only with
# mandatory wording ("must have/hold/possess", "requires", "... is required").

_OTHER_RE = re.compile(
    r"\b(?:must (?:have|hold|possess)|requires?) an? (?:active )?(?:\w+ )?security clearance\b"
    r"|\b(?:active )?security clearance (?:is )?required\b",
    re.IGNORECASE,
)


def _match_other(sentence: str) -> Match | None:
    match = _OTHER_RE.search(sentence)
    return ({"description": OTHER_SECURITY_CLEARANCE_LABEL}, match.start()) if match else None


# --- applies_at -----------------------------------------------------------------------------------

_APPLICATION_PHRASE_RE = re.compile(
    r"at the time of application|by the application deadline", re.IGNORECASE
)


def _applies_at(sentence: str) -> RequirementAppliesAt:
    return (
        RequirementAppliesAt.APPLICATION
        if _APPLICATION_PHRASE_RE.search(sentence)
        else RequirementAppliesAt.PROGRAM_START
    )


def _match_sentence(sentence: str) -> tuple[RequirementType, Match] | None:
    """At most one proposal per sentence. Order matches the ADR-012 §5 table."""
    for requirement_type, matcher in (
        (RequirementType.MINIMUM_AGE, _match_minimum_age),
        (RequirementType.EDUCATION, _match_education),
        (RequirementType.CITIZENSHIP, _match_citizenship),
        (RequirementType.WORK_AUTHORIZATION, _match_work_authorization),
        (RequirementType.OTHER, _match_other),
    ):
        found = matcher(sentence)
        if found is not None:
            return requirement_type, found
    return None


def _excerpt(sentence: str, position: int) -> str:
    """The sentence, or a window of at most MAX_EXCERPT_CHARS around the matched phrase, so the
    evidence always shows what the proposal is based on."""
    if len(sentence) <= MAX_EXCERPT_CHARS:
        return sentence
    # Room for an ellipsis on each cut side; the match starts a third of the way in.
    width = MAX_EXCERPT_CHARS - 2
    start = max(0, min(position - width // 3, len(sentence) - width))
    end = start + width
    return ("…" if start else "") + sentence[start:end] + ("…" if end < len(sentence) else "")


def _valid_value(requirement_type: RequirementType, value: dict[str, Any]) -> dict[str, Any] | None:
    schema = REQUIREMENT_VALUE_SCHEMAS.get(requirement_type)
    if schema is None:
        return value
    try:
        return schema.model_validate(value).model_dump(mode="json")
    except ValidationError:
        return None  # defensive: a matcher produced a shape its own schema rejects


def extract_requirements(inputs: ExtractionInput) -> tuple[Proposal, ...]:
    """Extract at most `MAX_PROPOSALS` proposals, in document order (title, then description),
    deduped by semantic key (first occurrence wins). Never raises on malformed input text."""
    proposals: list[Proposal] = []
    seen_keys: set[str] = set()

    for sentence in (*_sentences(inputs.title), *_sentences(inputs.description)):
        if _skipped(sentence):
            continue
        match = _match_sentence(sentence)
        if match is None:
            continue
        requirement_type, (raw_value, position) = match
        value = _valid_value(requirement_type, raw_value)
        if value is None:
            continue
        applies_at = _applies_at(sentence)
        key = semantic_key(requirement_type, value, applies_at, None)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        proposals.append(
            Proposal(
                requirement_type=requirement_type,
                value=value,
                applies_at=applies_at,
                reference_date=None,
                source_text=_excerpt(sentence, position),
            )
        )
        if len(proposals) == MAX_PROPOSALS:
            break

    return tuple(proposals)
