"""Deterministic requirement extraction, `requirements-rules` v1 (ADR-012 §5).

Pure: no network, no AI, no clock, no randomness. Same input always yields the same output.
Precision over recall: a sentence is only turned into a proposal when it explicitly states a
hard requirement in one of the forms below; anything hedged, vague, or ambiguous is left alone.
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
# "U.S." is the only abbreviation the extractor's own patterns care about; protecting its periods
# keeps "Must be a U.S. citizen." from splitting into two fragments.

_US_PLACEHOLDER = ""  # a Unicode private-use codepoint: won't collide with real text
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _protect_abbreviations(text: str) -> str:
    return re.sub(r"\bU\.S\.", f"U{_US_PLACEHOLDER}S{_US_PLACEHOLDER}", text)


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


# --- hedge / preference / vague-audience filter -------------------------------------------------
# Any of these anywhere in a sentence means the sentence is never a hard requirement: ADR-012 §5.

_HEDGE_RE = re.compile(
    r"\b(?:preferred|nice to have|bonus|ideally|ideal|typically|most|usually|encouraged|"
    r"welcome)\b|\bplus\b",
    re.IGNORECASE,
)


def _is_hedged(sentence: str) -> bool:
    return bool(_HEDGE_RE.search(sentence))


# --- minimum_age ----------------------------------------------------------------------------------

_AGE_PATTERNS = (
    re.compile(r"\bmust be at least (\d{1,3})\b", re.IGNORECASE),
    re.compile(r"\bminimum age[: ]+(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"\bmust be (\d{1,3}) years (?:of age|old) or older\b", re.IGNORECASE),
    re.compile(r"\bapplicants must be (?:at least )?(\d{1,3}) years of age\b", re.IGNORECASE),
)


def _match_minimum_age(sentence: str) -> dict[str, Any] | None:
    for pattern in _AGE_PATTERNS:
        match = pattern.search(sentence)
        if match is None:
            continue
        years = int(match.group(1))
        if MIN_PLAUSIBLE_AGE <= years <= MAX_PLAUSIBLE_AGE:
            return {"years": years}
        return None  # out-of-range age: the sentence is about age, but not a usable proposal
    return None


# --- education --------------------------------------------------------------------------------
# Mandatory enrollment language only; "senior", "teens", "young people" etc. never match because
# they aren't accepted lead-ins or level words.

_EDU_LEVELS = {
    "high school": EducationLevel.HIGH_SCHOOL,
    "undergraduate": EducationLevel.UNDERGRADUATE,
    "graduate": EducationLevel.GRADUATE,
}

_EDU_RE = re.compile(
    r"\b(?:must be (?:an? )?|currently enrolled (?:in )?(?:an? )?|must be enrolled in an? )"
    r"(?P<incoming>incoming |rising |entering )?"
    r"(?P<level>high school|undergraduate|graduate)"
    r"(?:\s+student[s]?)?(?:\s+program)?\b",
    re.IGNORECASE,
)

# A bare "incoming/rising/entering LEVEL student(s)" is itself an explicit, mandatory enrollment
# statement even without a leading "must be" / "currently enrolled".
_EDU_INCOMING_RE = re.compile(
    r"\b(?P<incoming>incoming|rising|entering)\s+(?P<level>high school|undergraduate|graduate)"
    r"\s+students?\b",
    re.IGNORECASE,
)


def _match_education(sentence: str) -> dict[str, Any] | None:
    match = _EDU_RE.search(sentence) or _EDU_INCOMING_RE.search(sentence)
    if match is None:
        return None
    level = _EDU_LEVELS[match.group("level").lower()]
    return {"levels": [level.value], "accepts_incoming": bool(match.group("incoming"))}


# --- citizenship ------------------------------------------------------------------------------
# Only "U.S." has a mapping in v1 (ADR-012 §5: "a small explicit table"). "U.S. person" and
# "citizen or permanent resident" are deliberately excluded: different legal concepts.

_CITIZENSHIP_RE = re.compile(
    r"\bmust be an? (?:U\.S\.|united states) citizen\b"
    r"|\b(?:U\.S\.|united states) citizens? only\b"
    r"|\b(?:U\.S\.|united states) citizenship(?: is)? required\b",
    re.IGNORECASE,
)


def _match_citizenship(sentence: str) -> dict[str, Any] | None:
    return {"countries": ["US"]} if _CITIZENSHIP_RE.search(sentence) else None


# --- work_authorization -------------------------------------------------------------------------

_WORK_AUTH_RE = re.compile(
    r"\bauthorized to work in the united states\b"
    r"|\bwork authorization(?: is)? required\b"
    r"|\bcitizen or permanent resident\b",
    re.IGNORECASE,
)


def _match_work_authorization(sentence: str) -> dict[str, Any] | None:
    return {"description": WORK_AUTH_LABEL} if _WORK_AUTH_RE.search(sentence) else None


# --- other --------------------------------------------------------------------------------------
# Used sparingly (ADR-012 §5): only hard requirements no evaluator rule covers.

_OTHER_RE = re.compile(
    r"\b(?:must have an? |requires? an? )?(?:active )?security clearance"
    r"(?: required| is required)?\b",
    re.IGNORECASE,
)


def _match_other(sentence: str) -> dict[str, Any] | None:
    return {"description": OTHER_SECURITY_CLEARANCE_LABEL} if _OTHER_RE.search(sentence) else None


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


def _match_sentence(sentence: str) -> tuple[RequirementType, dict[str, Any]] | None:
    """At most one proposal per sentence. Order matches the ADR-012 §5 table."""
    for requirement_type, matcher in (
        (RequirementType.MINIMUM_AGE, _match_minimum_age),
        (RequirementType.EDUCATION, _match_education),
        (RequirementType.CITIZENSHIP, _match_citizenship),
        (RequirementType.WORK_AUTHORIZATION, _match_work_authorization),
        (RequirementType.OTHER, _match_other),
    ):
        value = matcher(sentence)
        if value is not None:
            return requirement_type, value
    return None


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
        if _is_hedged(sentence):
            continue
        match = _match_sentence(sentence)
        if match is None:
            continue
        requirement_type, raw_value = match
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
                source_text=sentence[:MAX_EXCERPT_CHARS],
            )
        )

    return tuple(proposals[:MAX_PROPOSALS])
