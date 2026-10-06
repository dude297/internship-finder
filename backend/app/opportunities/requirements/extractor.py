"""Deterministic requirement extraction, `requirements-rules` v2 (ADR-012 §5).

Pure: no network, no AI, no clock, no randomness. Same input always yields the same output.
Precision over recall: a clause is only turned into a proposal when it explicitly states a hard
requirement in one of the forms below; anything hedged, negated, conditional, listed with
alternatives, about another role, or otherwise ambiguous is left alone.

v2 over v1: enrollment/degree variants, graduation windows, class standing, a corrected
citizenship / permanent-residency / export-control / work-authorization split, and age forms
without "years". Free-text (`other`, `work_authorization`) descriptions are FIXED labels from the
tables below, never copied text, so differently worded same-meaning text yields the same
semantic key. Details and the label table: docs/research/requirement-extractor-v2.md.
"""

import re
from datetime import date
from typing import Any, NamedTuple

from pydantic import BaseModel, ConfigDict, ValidationError

from app.enums import EducationLevel, RequirementAppliesAt, RequirementType
from app.opportunities.eligibility.schemas import REQUIREMENT_VALUE_SCHEMAS
from app.opportunities.requirements.identity import ExtractionInput, semantic_key

EXTRACTOR_NAME = "requirements-rules"
EXTRACTOR_VERSION = "3"

MAX_PROPOSALS = 20
MAX_EXCERPT_CHARS = 300
MIN_PLAUSIBLE_AGE = 10
MAX_PLAUSIBLE_AGE = 30

# v1 labels: unchanged so v1 reviewed decisions keep their semantic keys.
WORK_AUTH_LABEL = "Authorized to work in the United States"
OTHER_SECURITY_CLEARANCE_LABEL = "Security clearance required"
# v2 labels.
WORK_AUTH_NO_SPONSORSHIP_LABEL = "Authorized to work in the United States without sponsorship"
OTHER_CITIZEN_OR_PR_LABEL = "U.S. citizen or permanent resident"
OTHER_US_PERSON_LABEL = "U.S. person (export control)"
OTHER_RETURN_TO_SCHOOL_LABEL = "Must be returning to school after the internship"
_GRAD_PREFIX = "Expected graduation: "
_STANDING_PREFIX = "Class standing: "
_DASH = "\u2013"
_TITLE_PREFIX = "Posting title: "


class Proposal(BaseModel):
    """One extracted requirement proposal. Immutable; identity is `semantic_key`, never the
    source text or position."""

    model_config = ConfigDict(frozen=True)

    requirement_type: RequirementType
    value: dict[str, Any]
    applies_at: RequirementAppliesAt = RequirementAppliesAt.PROGRAM_START
    reference_date: date | None = None
    source_text: str


class _Hit(NamedTuple):
    requirement_type: RequirementType
    value: dict[str, Any]
    position: int
    applies_at: RequirementAppliesAt | None = None  # None: the default `_applies_at(clause)`
    reference_date: date | None = None


# --- sentence / clause splitting ------------------------------------------------------------------
# Sentences end at . ! ? and at line breaks and bullets (each <li> arrives as its own line). Dotted
# abbreviations ("U.S.", "B.S.", "Ph.D.", "e.g.") are protected. A sentence is then split at ";"
# into clauses; every guard and matcher works on one clause, so "Employees must be 18; interns
# must be 16" cannot leak the employee clause into the intern one.

_PLACEHOLDER = chr(0xE000)  # private-use codepoint: won't collide with real text
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\s*[\r\n]+\s*|\s*[•▪◦]\s*")
# Horizontal whitespace runs collapse first: `\s*` around the newline alternative backtracks
# quadratically over a long run of spaces (50,000 spaces took ~140 s), and a provider can send one.
_HORIZONTAL_SPACE_RUN = re.compile(r"[^\S\r\n]{2,}")
_DOTTED_ABBREVIATION = re.compile(r"\b(?:[A-Za-z]{1,2}\.){2,}|\bPh\.D\b")


_US_SENTENCE_END = re.compile(
    r"(\bU\.S\.(?:A\.)?)[ \t]+(?=(?:Interns?|Applicants?|Candidates?|Participants?|Mentors?|"
    r"Employees|Staff|Engineers|Managers|Supervisors|Contractors|Must|We|Our|You|Your|This|The|"
    r"All|Full)\b)"
)


def _protect_abbreviations(text: str) -> str:
    text = _US_SENTENCE_END.sub("\\1\n", text)  # "across the U.S. Mentors must" is two sentences
    return _DOTTED_ABBREVIATION.sub(lambda m: m.group().replace(".", _PLACEHOLDER), text)


def _restore_abbreviations(text: str) -> str:
    return text.replace(_PLACEHOLDER, ".")


def _clauses(text: str | None) -> list[str]:
    if not text:
        return []
    clauses: list[str] = []
    text = _HORIZONTAL_SPACE_RUN.sub(" ", text)
    for sentence in _SENTENCE_BOUNDARY.split(_protect_abbreviations(text)):
        for clause in sentence.split(";"):
            restored = _restore_abbreviations(clause).strip()
            if restored:
                clauses.append(restored)
    return clauses


# --- clause-level guards --------------------------------------------------------------------------
# Hedges, preferences, conditionals and exceptions: never a hard requirement. "may" is a hedge
# except when it is the month ("graduating in May 2028").

_HEDGE_RE = re.compile(
    r"\b(?:preferred|prefer|prefers|preference|nice to have|bonus|ideally|ideal|desirable|desired|"
    r"favou?red|typically|generally|normally|commonly|often|sometimes|mostly|primarily|most|"
    r"usually|encouraged|welcome|might|could|unless|except|exceptions?|waivers?|depending|"
    r"some|certain|select|several|"
    r"if)\b|\bmay\b(?!\s+(?:\d|apply\b|participate\b|be\s+(?:considered|eligible)\b))|"
    r"\bplus\b|\bcase[- ]by[- ]case\b|\ba plus\b",
    re.IGNORECASE,
)
# Form questions ("asked whether you are authorized to work") describe the application, not a rule.
_QUESTION_RE = re.compile(r"\b(?:whether|asks?|asked|questions?|indicate)\b", re.IGNORECASE)
# Negations, "does not affect", "regardless of", "all ages", and upper bounds invert or void an
# otherwise matching phrase.
_NEGATION_RE = re.compile(
    r"\b(?:not|no|never|cannot|can't|don't|doesn't|isn't|aren't|won't|nor|neither|ineligible|"
    r"regardless|irrespective|without regard|no matter|optional|exempt|waived|all ages|any age|"
    r"all nationalities|any nationality)\b|\bnon[-\s]|\bor (?:younger|under|less)\b"
    r"|\bunder the age\b|\bunder \d|n't\b",
    re.IGNORECASE,
)
# "no earlier than" / "no later than" are bounds on a date, not negations of the requirement.
_DATE_BOUND_NEGATION_RE = re.compile(
    r"\b(?:no|not) (?:earlier|later) than\b|\bnot before\b", re.IGNORECASE
)
# A clause about another role ("employees must be 18", "mentors must hold a clearance") says
# nothing about the interns, unless it also names the intern-side audience.
_OTHER_ROLE_RE = re.compile(
    r"\b(?:employees?|staff|full[- ]time (?:hires?|employees?)|mentors?|supervisors?|managers?|"
    r"parents?|guardians?|chaperones?|instructors?|teachers?|drivers?|alumni|judges?|engineers|"
    r"scientists|developers|researchers|analysts|contractors?|consultants?|vendors?|freelancers?|"
    r"conversions?|return\s+offers?|post[- ]graduat\w+|post[- ]internship|"
    r"full[- ]time\s+(?:offers?|employment))\b",
    re.IGNORECASE,
)
_INTERN_SIDE_RE = re.compile(
    r"\b(?:interns?|students?|applicants?|candidates?|participants?|you|your|fellows?)\b",
    re.IGNORECASE,
)
# A mandatory lead-in: the clause is phrased as a condition of eligibility rather than a
# description of the program.
_LEAD_RE = re.compile(
    r"\b(?:must|only|required?|requires?|requirements?|qualifications?|eligib\w+|open\s+to|"
    r"restricted\s+to|limited\s+to|need\s+to|needs\s+to|have\s+to|you\s+are|you're|"
    r"you\s+will\s+be|applicants?|candidates?|participants?|who\s+(?:are|is|have|will)|"
    r"to\s+apply)\b",
    re.IGNORECASE,
)
_LEADING_FILLER_RE = re.compile(r"[\W_]*(?:(?:and|also|a|an|current|currently)\s+)*", re.IGNORECASE)
_FOREIGN_COUNTRY_RE = re.compile(
    r"\b(?:Canada|Canadian|UK|United Kingdom|Europe|European|EU|Mexico|Mexican|India|Indian|"
    r"Germany|German|Australia|Australian|British|Irish|Ireland|Japan|Japanese|China|Chinese|"
    r"France|French|Israel|Israeli|Korea|Korean|Singapore|New Zealand|NZ|Brazil|Brazilian)\b"
    r"|\bU\.K\."
)


def _other_role_only(clause: str) -> bool:
    return bool(_OTHER_ROLE_RE.search(clause)) and not _INTERN_SIDE_RE.search(clause)


def _has_lead(clause: str, start: int) -> bool:
    """Mandatory wording anywhere in the clause, or the matched phrase opens the clause (a bare
    bullet such as "Currently pursuing a BS" or "Authorized to work in the United States")."""
    return bool(_LEAD_RE.search(clause) or _LEADING_FILLER_RE.fullmatch(clause[:start]))


# --- shared vocabulary ----------------------------------------------------------------------------

# "US"/"USA" only in capitals so the pronoun "us" never matches.
_US = r"(?:the\s+)?(?:U\.S\.A?\.?|(?-i:USA?)\b|United\s+States(?:\s+of\s+America)?)"
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH_ABBREV = {number: name.capitalize() for name, number in _MONTHS.items()}
_MONTH_ALT = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
}

_DATE_MDY_RE = re.compile(
    rf"\b(?P<m>{_MONTH_ALT})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y>20\d\d)\b",
    re.IGNORECASE,
)
_DATE_DMY_RE = re.compile(
    rf"\b(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<m>{_MONTH_ALT})\.?,?\s+(?P<y>20\d\d)\b",
    re.IGNORECASE,
)
_DATE_ISO_RE = re.compile(r"\b(?P<y>20\d\d)-(?P<m>\d\d)-(?P<d>\d\d)\b")
_PARTIAL_DATE_RE = re.compile(
    rf"\b(?:as of|by|before|on|starting|beginning)\s+(?:the\s+)?(?:{_MONTH_ALT})\b", re.IGNORECASE
)


def _month_number(text: str) -> int:
    return _MONTHS[text[:3].lower()]


def _explicit_date(text: str) -> date | None:
    """A full year-bearing calendar date in the text, if any."""
    for pattern in (_DATE_MDY_RE, _DATE_DMY_RE, _DATE_ISO_RE):
        match = pattern.search(text)
        if match is None:
            continue
        month = int(match["m"]) if match["m"].isdigit() else _month_number(match["m"])
        try:
            return date(int(match["y"]), month, int(match["d"]))
        except ValueError:
            return None
    return None


# --- minimum_age ----------------------------------------------------------------------------------
# The number must be an age: "years (of age|old)", "or older", or ending the clause. "at least 18
# months into the degree", "at least 20 hours per week" and "at least 5 years of experience" are
# never ages.

_YEARS = (
    r"(?:\s+years?(?:\s+(?:of\s+age|old))?\b(?!\s+(?:of\s+(?!age\b)|in\b|working|experience)))?"
)
_OLDER = r"\s*(?:\+|or\s+(?:older|over|above)|and\s+(?:older|over|above|up))"
# "must be 21 to drive company vehicles": an age for an activity, not for the program.
_AGE_NOT_FOR_RE = re.compile(
    r"\s+to\s+(?:drive|operate|rent|purchase|buy|handle|serve|use|enter|attend|travel|access|"
    r"carry|lift|work\s+(?:with|on|around|near))\b",
    re.IGNORECASE,
)
_AGE_END = (
    r"(?=\s*(?:[.,;:)]|$|\b(?:at|by|on|as of|when|before|prior to|and|in order|is|"
    r"required|needed)\b|\bto\s+(?:apply|participate|join|enroll|intern|start|begin|qualify|"
    r"be\s+(?:eligible|considered)|work\b(?!\s+(?:with|on|around|near)\b))))"
)
# "Interns who are 18 or older" in a sentence about peers is not a requirement: the number needs
# an explicit requirement subject.
_AGE_LEAD = (
    r"(?:must\s+be|need\s+to\s+be|needs\s+to\s+be|have\s+to\s+be|required\s+to\s+be|"
    r"should\s+be|(?:you|applicants?|candidates?|participants?)\s+(?:are|is|be)|"
    r"(?:applicants?|candidates?|participants?)\s+who\s+are)"
)
_AGE_PATTERNS = (
    re.compile(
        rf"\b{_AGE_LEAD}\s+at\s+least\s+"
        r"(?P<n>\d{1,3})" + _YEARS + _AGE_END,
        re.IGNORECASE,
    ),
    re.compile(
        r"\bminimum\s+age(?:\s+of|\s+is|:)?\s+(?P<n>\d{1,3})" + _YEARS + _AGE_END, re.IGNORECASE
    ),
    re.compile(
        rf"\b{_AGE_LEAD}\s+(?P<n>\d{{1,3}})"
        r"(?:\s+years?(?:\s+(?:of\s+age|old))?)?" + _OLDER + r"(?!\w)",
        re.IGNORECASE,
    ),
    re.compile(r"\bages?\s+(?P<n>\d{1,3})" + _OLDER + r"(?!\w)", re.IGNORECASE),  # needs lead
    re.compile(r"\bapplicants\s+must\s+be\s+(?:at\s+least\s+)?(?P<n>\d{1,3})\s+years\s+of\s+age\b"),
    re.compile(r"\bat\s+least\s+(?P<n>\d{1,3})\s+years?\s+(?:of\s+age|old)\b", re.IGNORECASE),
)
_NEEDS_LEAD = (_AGE_PATTERNS[3], _AGE_PATTERNS[5])
_TAIL_PREP_RE = re.compile(
    r"\s*,?\s*(?P<prep>by|on|as of|before|prior to|at|when|no later than)\b(?P<rest>.*)",
    re.IGNORECASE,
)
_APPLICATION_TIMING_RE = re.compile(
    r"time of (?:application|applying)|application (?:deadline|date|submission)|\bapplying\b|"
    r"submission",
    re.IGNORECASE,
)
_PROGRAM_START_TIMING_RE = re.compile(
    r"(?:start|begin|beginning|commence|commencement)\b|start date|time of (?:hire|hiring)|"
    r"onboarding|first day",
    re.IGNORECASE,
)
_APPLICATION_PHRASE_RE = re.compile(
    r"at the time of application|by the application deadline|when (?:you )?appl(?:y|ying)",
    re.IGNORECASE,
)
_AGE_PROGRAM_PHRASE_RE = re.compile(r"\b(?:internship|program|role|job)\b", re.IGNORECASE)


def _applies_at(clause: str) -> RequirementAppliesAt:
    return (
        RequirementAppliesAt.APPLICATION
        if _APPLICATION_PHRASE_RE.search(clause)
        else RequirementAppliesAt.PROGRAM_START
    )


def _age_timing(clause: str, end: int) -> tuple[RequirementAppliesAt, date | None] | None:
    """The timing the age is checked at, or None when a date follows that we cannot place:
    "at least 16 by June 1" (no year) is neither silently program_start nor an explicit date."""
    tail = _TAIL_PREP_RE.match(clause, end)
    if tail is None:
        return _applies_at(clause), None
    rest = tail["rest"]
    explicit = _explicit_date(rest)
    if explicit is not None:
        return RequirementAppliesAt.EXPLICIT_DATE, explicit
    if _APPLICATION_TIMING_RE.search(rest):
        return RequirementAppliesAt.APPLICATION, None
    if _PROGRAM_START_TIMING_RE.search(rest):
        return RequirementAppliesAt.PROGRAM_START, None
    return None


def _match_minimum_age(clause: str) -> list[_Hit]:
    for pattern in _AGE_PATTERNS:
        match = pattern.search(clause)
        if match is None:
            continue
        if pattern in _NEEDS_LEAD and not _has_lead(clause, match.start()):
            continue
        years = int(match["n"])
        if _AGE_NOT_FOR_RE.match(clause, match.end()):
            return []
        if not MIN_PLAUSIBLE_AGE <= years <= MAX_PLAUSIBLE_AGE:
            return []  # about age, but not a usable proposal
        timing = _age_timing(clause, match.end())
        if timing is None:
            return []
        applies_at, reference_date = timing
        return [
            _Hit(
                RequirementType.MINIMUM_AGE,
                {"years": years},
                match.start(),
                applies_at,
                reference_date,
            )
        ]
    return []


# --- education ------------------------------------------------------------------------------------
# Mandatory enrollment language only. A clause naming more than one level ("Bachelor's or Master's",
# "a high school student, undergraduate, or graduate student") is a list of alternatives that one
# level would misrepresent: skipped. "a graduate of", "a high school graduate", "a high school
# diploma" describe a finished level, never current enrollment. Bare "college student" is not
# undergraduate-only (graduate students are college students): only "four-year", "undergraduate",
# or bachelor's wording is.

_LEVEL_TOKEN = (
    r"(?P<lvl>high[- ]school|undergrad(?:uate)?|graduate|bachelor['’]?s|bachelors|master['’]?s|"
    r"masters|doctoral|ph\.?d|(?-i:BS|BA|BSc|BEng|B\.S\.|B\.A\.|MS|MSc|MA|M\.S\.))"
)
# Counts plural forms ("undergraduates", "graduates") and associate degrees (a level with no
# EducationLevel) so that any second level in the clause makes it a list of alternatives.
_LEVEL_ANY_RE = re.compile(
    rf"(?<!\w)(?:{_LEVEL_TOKEN.replace('?P<lvl>', '')}s?|associate['’]?s?(?=\s+(?:degree|program)))"
    r"(?!\w)",
    re.IGNORECASE,
)
# "bachelor's degree or higher", "undergraduate student or a bootcamp participant": the level is
# one of several accepted statuses.
_ALT_AFTER_LEVEL_RE = re.compile(
    r"\s*(?:,\s*)?(?:or|and/or|/)\s+"
    r"(?!(?:freshm\w*|sophomores?|juniors?|seniors?|first[- ]year|students?)\b)",
    re.IGNORECASE,
)
_ALT_BEFORE_RE = re.compile(r"\b(?:or|and/or)(?:\s+(?:be|are))?(?:\s+an?)?\s*$", re.IGNORECASE)
_APPLY_ACTION_RE = re.compile(
    r"\b(?:apply|applying|application|submit\w*|deadline|due|register\w*|respond\w*|send)\b",
    re.IGNORECASE,
)
_INCOMING = r"(?P<inc>incoming|rising|entering)"
_NOUN = r"(?P<noun>students?|seniors?|juniors?|sophomores?|freshm[ae]n)"
_EDU_ALTERNATIVE_RE = re.compile(
    r"\b(?:equivalent|in lieu)\b|\b(?:recent|new)\s+(?:grad|grads|graduates?)\b|"
    r"\bor\s+(?:alumn\w+|career\s+changers?)\b|\brecent\s+alumn\w+",
    re.IGNORECASE,
)
_TAIL = (
    r"(?:\s+(?:degree|program|programme|students?|studies|coursework|school)\b"
    r"|(?=\s*(?:[.,;:)]|$|\b(?:in|or|and|at|with|from|majoring|studying)\b)))"
)
_EDU_PURSUIT_RE = re.compile(
    r"\b(?P<cur>currently\s+|actively\s+|presently\s+)?"
    r"(?:pursuing|enrolled\s+(?:(?:full|part)[- ]time\s+)?(?:in|as)|working\s+towards?)\s+"
    r"(?:an?\s+|their\s+|your\s+)?"
    r"(?:(?:full[- ]time|part[- ]time|accredited|four[- ]year|4[- ]year)\s+)*"
    + _LEVEL_TOKEN
    + _TAIL,
    re.IGNORECASE,
)
_EDU_STUDENT_RE = re.compile(
    rf"\b{_INCOMING}?\s*(?P<cur>current(?:ly)?\s+(?:(?:an?|enrolled)\s+)*)?"
    rf"{_LEVEL_TOKEN}\s+{_NOUN}\b",
    re.IGNORECASE,
)
_EDU_HS_GRADE_IN_RE = re.compile(
    rf"\b{_INCOMING}\s+(?:(?:freshm[ae]n|sophomores?|juniors?|seniors?)(?:\s*(?:,|and|or|/)\s*)*)+"
    r"\s+(?:in|at)\s+high[- ]school\b",
    re.IGNORECASE,
)
_EDU_FOUR_YEAR_RE = re.compile(
    r"\b(?:currently\s+)?(?:enrolled\s+(?:in|at)|attending|student\s+(?:at|in))\s+(?:an?\s+)?"
    r"(?:accredited\s+)?(?:four|4)[- ]year\s+(?:accredited\s+)?"
    r"(?:college|university|institution|school)",
    re.IGNORECASE,
)
_EDU_FRESHMAN_RE = re.compile(
    r"\b(?P<inc>incoming|entering)\s+(?:first[- ]year|freshm[ae]n)\b", re.IGNORECASE
)
_COLLEGE_CONTEXT_RE = re.compile(r"\b(?:colleges?|universit(?:y|ies))\b", re.IGNORECASE)
_HIGH_SCHOOL_CONTEXT_RE = re.compile(r"\bhigh[- ]school|\bgrades?\b|\bsecondary school", re.I)
_CURRENT_RE = re.compile(r"\bcurrent(?:ly)?\b", re.IGNORECASE)
_DURING_RE = re.compile(
    r"\bduring\s+the\s+(?:internship|program|summer|term)|\bthroughout\b|"
    r"\bat\s+the\s+start\b|\bprogram\s+start\b|\bwhen\s+the\s+(?:internship|program)\s+(?:begins|starts)\b",
    re.IGNORECASE,
)


def _level_of(token: str) -> EducationLevel | None:
    lowered = token.lower().replace("-", " ")
    if lowered == "high school":
        return EducationLevel.HIGH_SCHOOL
    if token in {"BS", "BA", "BSc", "BEng", "B.S.", "B.A."} or lowered.startswith(
        ("undergrad", "bachelor")
    ):
        return EducationLevel.UNDERGRADUATE
    if token in {"MS", "MSc", "MA", "M.S."} or lowered in {
        "graduate",
        "masters",
        "master's",
        "master’s",
        "doctoral",
        "phd",
        "ph.d",
    }:
        return EducationLevel.GRADUATE
    return None


def _education_timing(
    clause: str, current: bool
) -> tuple[RequirementAppliesAt, date | None] | None:
    """application for "current(ly)" / "at the time of application"; program_start for "during the
    internship" and the default; explicit_date for a year-bearing date. None: a date was named
    that cannot be placed (month without year/day)."""
    explicit = _explicit_date(clause)
    if explicit is not None and _APPLY_ACTION_RE.search(clause):
        explicit = None  # "must apply by March 1, 2027" is a deadline, not an enrollment date
    if explicit is not None and re.search(
        r"\b(?:as of|by|before|on|starting|beginning|from)\b", clause, re.IGNORECASE
    ):
        return RequirementAppliesAt.EXPLICIT_DATE, explicit
    if _PARTIAL_DATE_RE.search(clause):
        return None
    if _DURING_RE.search(clause):
        return RequirementAppliesAt.PROGRAM_START, None
    if current or _APPLICATION_PHRASE_RE.search(clause):
        return RequirementAppliesAt.APPLICATION, None
    return RequirementAppliesAt.PROGRAM_START, None


def _education_hit(
    clause: str, level: EducationLevel, incoming: bool, current: bool, position: int
) -> list[_Hit]:
    timing = _education_timing(clause, current)
    if timing is None:
        return []
    applies_at, reference_date = timing
    value = {"levels": [level.value], "accepts_incoming": incoming}
    return [_Hit(RequirementType.EDUCATION, value, position, applies_at, reference_date)]


_FOUR_YEAR_ALT_RE = re.compile(
    r"\s*(?:,\s*)?(?:or|and/or|/)\s+(?!(?:university|college|institution|school)\b)", re.IGNORECASE
)
# "... or be a current graduate student": the status is one branch of an "or" list.
_OR_GRADUATE_BRANCH_RE = re.compile(
    r"\bor\b[^.;]*\b(?:graduate\s+students?|alumn\w+|master['’]?s|ph\.?d|recent\s+grad\w*)",
    re.IGNORECASE,
)


def _is_alternative(clause: str, match: re.Match[str]) -> bool:
    """The matched status is one branch of an "or" list ("... or higher", "X or be a graduate
    student"), so a single-level proposal would misstate it."""
    return bool(
        _ALT_AFTER_LEVEL_RE.match(clause, match.end())
        or _ALT_BEFORE_RE.search(clause[: match.start()])
    )


def _match_education(clause: str) -> list[_Hit]:
    levels = {_level_of(m.group()) for m in _LEVEL_ANY_RE.finditer(clause)}
    if len(levels) > 1 or _EDU_ALTERNATIVE_RE.search(clause):
        return []

    match = _EDU_PURSUIT_RE.search(clause)
    if match is not None and _is_alternative(clause, match):
        return []
    if match is not None and _has_lead(clause, match.start()):
        level = _level_of(match["lvl"])
        if level is not None:
            return _education_hit(
                clause,
                level,
                False,
                bool(match["cur"]) or bool(_CURRENT_RE.search(clause)),
                match.start(),
            )

    match = _EDU_STUDENT_RE.search(clause)
    if match is not None and _is_alternative(clause, match):
        return []
    if match is not None:
        level = _level_of(match["lvl"])
        noun = match["noun"].lower()
        noun_ok = level is EducationLevel.HIGH_SCHOOL or noun.startswith("student")
        # A bare "incoming/rising" is itself a mandatory enrollment statement (v1 behavior);
        # otherwise the clause needs mandatory wording.
        mandatory = match["inc"] or match["cur"] or _LEAD_RE.search(clause)
        if level is not None and noun_ok and mandatory:
            return _education_hit(
                clause, level, bool(match["inc"]), bool(match["cur"]), match.start()
            )

    match = _EDU_HS_GRADE_IN_RE.search(clause)
    if match is not None:
        return _education_hit(
            clause,
            EducationLevel.HIGH_SCHOOL,
            True,
            bool(_CURRENT_RE.search(clause)),
            match.start(),
        )

    match = _EDU_FOUR_YEAR_RE.search(clause)
    if match is not None and _FOUR_YEAR_ALT_RE.match(clause, match.end()):
        return []
    if match is not None and _has_lead(clause, match.start()):
        return _education_hit(
            clause,
            EducationLevel.UNDERGRADUATE,
            False,
            bool(_CURRENT_RE.search(clause)),
            match.start(),
        )

    match = _EDU_FRESHMAN_RE.search(clause)
    if (
        match is not None
        and _COLLEGE_CONTEXT_RE.search(clause)
        and not _HIGH_SCHOOL_CONTEXT_RE.search(clause)
    ):
        return _education_hit(clause, EducationLevel.UNDERGRADUATE, True, False, match.start())
    return []


# "Must return to school after the internship": enrollment status after the program, which the
# education value cannot represent.
_RETURN_TO_SCHOOL_RE = re.compile(
    r"\b(?:must|required\s+to|need\s+to|have\s+to|expected\s+to|only|eligible\s+(?:if|for))"
    r"(?:\s+(?:be|intend\s+to|currently))*\s*(?:return(?:ing)?\s+to\s+"
    r"(?:school|(?:their|your)\s+(?:studies|degree|university|college)|(?:a\s+)?(?:college|"
    r"university|campus|classes)))",
    re.IGNORECASE,
)


def _match_return_to_school(clause: str) -> list[_Hit]:
    match = _RETURN_TO_SCHOOL_RE.search(clause)
    if match is None:
        return []
    return [
        _Hit(RequirementType.OTHER, {"description": OTHER_RETURN_TO_SCHOOL_LABEL}, match.start())
    ]


# --- graduation window ----------------------------------------------------------------------------
# No requirement type exists, so graduation windows become `other` with a normalized label such as
# "Expected graduation: Dec 2027 – Jun 2029". Only mandatory statements; a specific day, an
# unplaceable shape, or an inverted range yields nothing.


def _my(n: int) -> str:
    return (
        rf"(?:(?P<m{n}>{_MONTH_ALT})\.?,?\s+)?(?:(?P<d{n}>\d{{1,2}})(?:st|nd|rd|th)?,?\s+)?"
        rf"(?P<y{n}>20\d\d)"
    )


_GRAD_KEY = (
    r"(?:expected\s+graduation(?:\s+date)?|anticipated\s+graduation(?:\s+date)?|"
    r"graduation(?:\s+(?:date|year))?|graduating|graduates?|class\s+of)"
)
_GRAD_FILL = (
    r"(?:\s*(?:date|year|is|are|will\s+be|must\s+be|should\s+be|expected|anticipated|to\s+be|of)"
    r"(?=\W))*\s*:?\s*"
)
_GRAD_SEP = r"\s*(?:and|to|through|until|-|\u2013|\u2014)\s*"
_GRAD_RANGE_RE = re.compile(
    rf"\b{_GRAD_KEY}{_GRAD_FILL}(?:(?:between|from)\s+)?{_my(1)}{_GRAD_SEP}{_my(2)}", re.I
)
_GRAD_BOUND_RE = re.compile(
    rf"\b{_GRAD_KEY}{_GRAD_FILL}(?P<rel>after|later\s+than|following|on\s+or\s+after|"
    r"at\s+or\s+after|no\s+earlier\s+than|not\s+earlier\s+than|before|earlier\s+than|"
    rf"prior\s+to|on\s+or\s+before|at\s+or\s+before|no\s+later\s+than|not\s+later\s+than|by)\s+"
    rf"{_my(1)}",
    re.IGNORECASE,
)
_GRAD_OPEN_RE = re.compile(
    rf"\b{_GRAD_KEY}{_GRAD_FILL}(?:(?:in|during|on)\s+)?{_my(1)}\s+(?P<rel>or\s+later|and\s+later|"
    r"or\s+after|and\s+beyond|or\s+earlier|or\s+before)\b",
    re.IGNORECASE,
)
_GRAD_LIST_RE = re.compile(
    rf"\b{_GRAD_KEY}{_GRAD_FILL}(?:(?:in|during|on)\s+)?(?:the\s+year\s+)?{_my(1)}"
    r"(?P<more>(?:\s*(?:,|or|and|/)\s*(?:or\s+|and\s+)?20\d\d\b)*)",
    re.IGNORECASE,
)
_GRAD_BOUND_LABELS = {
    "after": "after",
    "later than": "after",
    "following": "after",
    "on or after": "on or after",
    "at or after": "on or after",
    "no earlier than": "on or after",
    "not earlier than": "on or after",
    "before": "before",
    "earlier than": "before",
    "prior to": "before",
    "on or before": "on or before",
    "at or before": "on or before",
    "no later than": "on or before",
    "not later than": "on or before",
    "by": "on or before",
}


def _my_value(match: re.Match[str], n: int) -> tuple[tuple[int, int], str] | None:
    """(sort key, label) for the n-th month/year group; None when a day is given or the year is
    implausible."""
    if match[f"d{n}"]:
        return None
    year = int(match[f"y{n}"])
    if not 2015 <= year <= 2060:
        return None
    month = match[f"m{n}"]
    if month is None:
        return (year, 0), str(year)
    number = _month_number(month)
    return (year, number), f"{_MONTH_ABBREV[number]} {year}"


def _grad_hit(label: str, position: int) -> list[_Hit]:
    return [_Hit(RequirementType.OTHER, {"description": _GRAD_PREFIX + label}, position)]


def _match_graduation(clause: str) -> list[_Hit]:
    if not _LEAD_RE.search(clause) and not re.match(
        rf"[\W_]*(?:(?:expected|anticipated)\s+to\s+)?{_GRAD_KEY}", clause, re.IGNORECASE
    ):
        return []

    if _OR_GRADUATE_BRANCH_RE.search(clause):
        return []

    match = _GRAD_RANGE_RE.search(clause)
    if match is not None:
        first, second = _my_value(match, 1), _my_value(match, 2)
        if first is None or second is None or first[0] > second[0]:
            return []
        return _grad_hit(f"{first[1]} {_DASH} {second[1]}", match.start())

    match = _GRAD_BOUND_RE.search(clause)
    if match is not None:
        point = _my_value(match, 1)
        relation = _GRAD_BOUND_LABELS.get(re.sub(r"\s+", " ", match["rel"].lower()))
        if point is None or relation is None:
            return []
        return _grad_hit(f"{relation} {point[1]}", match.start())

    match = _GRAD_OPEN_RE.search(clause)
    if match is not None:
        point = _my_value(match, 1)
        if point is None:
            return []
        relation = (
            "on or after"
            if match["rel"].lower().split()[-1] in {"later", "after", "beyond"}
            else "on or before"
        )
        return _grad_hit(f"{relation} {point[1]}", match.start())

    match = _GRAD_LIST_RE.search(clause)
    if match is not None:
        point = _my_value(match, 1)
        if point is None:
            return []
        extra = [int(y) for y in re.findall(r"20\d\d", match["more"])]
        if re.match(
            rf"\s*(?:,|or|and|/)\s*(?:or\s+|and\s+)?{_MONTH_ALT}\b", clause[match.end() :], re.I
        ):
            return []  # "December 2027 or June 2028": a list of dates we do not model
        if not extra:
            return _grad_hit(point[1], match.start())
        if point[0][1] != 0:  # "Dec 2027 or 2028" mixes shapes
            return []
        years = sorted({point[0][0], *extra})
        if any(not 2015 <= year <= 2060 for year in years):
            return []
        consecutive = all(b - a == 1 for a, b in zip(years, years[1:], strict=False))
        label = (
            f"{years[0]} {_DASH} {years[-1]}"
            if consecutive and len(years) > 1
            else " or ".join(str(y) for y in years)
        )
        return _grad_hit(label, match.start())
    return []


# --- academic standing ----------------------------------------------------------------------------
# "rising sophomore", "first-year student", "junior standing", "completed two semesters": not
# representable by the education value, so `other` with a normalized label. "senior" alone is
# ambiguous (high school vs college), so any "senior" label needs college/university/degree context;
# any standing clause mentioning high school or grades is skipped.

_STANDING_ORDER = ("first-year", "sophomore", "junior", "senior")
_STANDING_WORD = r"(?P<w>first[- ]year|freshm[ae]n|sophomores?|juniors?|seniors?)"
_RISING_STANDING_RE = re.compile(
    r"\brising\s+(?P<words>(?:(?:first[- ]year|freshm[ae]n|sophomores?|juniors?|"
    r"seniors?)(?:\s*(?:,|and|or|/|&)\s*)*)+)",
    re.IGNORECASE,
)
_STANDING_STUDENT_RE = re.compile(
    r"\b(?:must\s+be|are|is|be)\s+(?:an?\s+)?(?:current(?:ly)?\s+)?"
    rf"{_STANDING_WORD}\s+(?:students?\b|standing\b)",
    re.IGNORECASE,
)
_STANDING_STANDING_RE = re.compile(
    r"\b(?P<words>(?:(?:sophomore|junior|senior)(?:\s*(?:,|or|/)\s*)*)+)\s+standing"
    r"(?P<above>\s+or\s+(?:above|higher|later))?",
    re.IGNORECASE,
)
_FIRST_YEAR_STUDENT_RE = re.compile(
    r"\b(?:must\s+be|are|is|be)\s+(?:an?\s+)?(?:current(?:ly)?\s+)?first[- ]year\s+students?\b",
    re.IGNORECASE,
)
_DEGREE_CONTEXT_RE = re.compile(
    r"\b(?:colleges?|universit(?:y|ies)|undergraduate|undergrad|bachelor['’]?s|degree|campus)\b",
    re.I,
)
_COMPLETED_RE = re.compile(
    r"\b(?:must\s+have\s+completed|have\s+completed|has\s+completed|completed)\s+"
    r"(?:at\s+least\s+|a\s+minimum\s+of\s+)?(?P<n>\d{1,2}|one|two|three|four|five|six|seven|"
    r"eight)\s+(?P<unit>semesters?|quarters?|terms?|years?)\b(?P<rest>.{0,40})",
    re.IGNORECASE,
)


_GRADUATE_WORD_RE = re.compile(
    r"\bgraduate\s+(?:students?|programs?|school|degrees?)\b|\bmaster['’]?s\b|\bph\.?d\b|"
    r"\bdoctoral\b|\bmasters\b",
    re.IGNORECASE,
)
_STUDY_REST_RE = re.compile(
    r"^\s*(?:of\s+|toward\s+|towards\s+)?(?:a\s+|your\s+)?(?:college|university|undergraduate|study|studies|school|coursework|"
    r"a\s+degree|your\s+degree|full[- ]time\s+study)|^\s*(?:[.,;:)]|$)",
    re.IGNORECASE,
)


def _standing_words(text: str) -> list[str]:
    found: set[str] = set()
    for raw in re.findall(r"first[- ]year|freshm[ae]n|sophomore|junior|senior", text, re.I):
        word = raw.lower()
        found.add("first-year" if word.startswith(("first", "fresh")) else word)
    return [w for w in _STANDING_ORDER if w in found]


def _join_words(words: list[str]) -> str:
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " or " + words[-1]


def _standing_hit(label: str, position: int) -> list[_Hit]:
    return [_Hit(RequirementType.OTHER, {"description": _STANDING_PREFIX + label}, position)]


def _match_standing(clause: str) -> list[_Hit]:
    if (
        _HIGH_SCHOOL_CONTEXT_RE.search(clause)
        or _GRADUATE_WORD_RE.search(clause)
        or _EDU_ALTERNATIVE_RE.search(clause)
    ):
        return []  # a standing next to a graduate/high-school branch is one option of several
    degree = bool(_DEGREE_CONTEXT_RE.search(clause))

    match = _RISING_STANDING_RE.search(clause)
    if match is not None and _has_lead(clause, match.start()):
        words = _standing_words(match["words"])
        if words and ("senior" not in words or degree):
            return _standing_hit(f"rising {_join_words(words)}", match.start())
        return []

    match = _STANDING_STANDING_RE.search(clause)
    if match is not None:
        words = _standing_words(match["words"])
        if words and ("senior" not in words or degree):
            suffix = " or above" if match["above"] else ""
            return _standing_hit(_join_words(words) + suffix, match.start())
        return []

    match = _FIRST_YEAR_STUDENT_RE.search(clause)
    if match is not None:
        return _standing_hit("first-year", match.start())

    match = _STANDING_STUDENT_RE.search(clause)
    if match is not None:
        words = _standing_words(match["w"])
        if words and ("senior" not in words or degree) and words != ["first-year"]:
            return _standing_hit(words[0], match.start())
        return []

    match = _COMPLETED_RE.search(clause)
    if match is not None:
        unit = match["unit"].lower().rstrip("s")
        # "completed 2 years" can be work experience; only study context makes it standing.
        # "completed 2 semesters of calculus" / "2 terms of mentoring" are not class standing.
        if not _STUDY_REST_RE.match(match["rest"]) and not (
            unit == "year"
            and (degree or re.search(r"coursework|study|studies|school", match["rest"], re.I))
        ):
            return []
        raw = match["n"].lower()
        count = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
        if count < 1:
            return []
        label = f"Completed at least {count} {unit}{'' if count == 1 else 's'}"
        return [_Hit(RequirementType.OTHER, {"description": label}, match.start())]
    return []


# --- citizenship / residency / export control / work authorization -------------------------
# These categories are never collapsed into each other: citizenship alone is evaluated
# ("citizenship"); "citizen OR permanent resident" is a broader fact (`other`); "U.S. person" /
# export control is its own fact; "authorized to work" is `work_authorization`.

_CIT = r"(?:citizens?|citizenship)"
_CITIZENSHIP_PATTERNS = (
    re.compile(
        rf"\b(?:must|need\s+to|needs\s+to|required\s+to|have\s+to)\s+(?:be|hold|have)\s+"
        rf"(?:an?\s+)?{_US}\s+{_CIT}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:must|need\s+to|needs\s+to|required\s+to|have\s+to)\s+be\s+(?:an?\s+)?"
        rf"citizens?\s+of\s+{_US}",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b{_US}\s+citizens?\s+only\b|\bonly\s+{_US}\s+citizens?\b"
        rf"|\bonly\s+citizens?\s+of\s+{_US}"
        rf"|\b(?:open|limited|restricted|available)\s+(?:only\s+)?to\s+(?:{_US}\s+citizens?"
        rf"|citizens?\s+of\s+{_US})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b{_US}\s+citizenship\s+(?:is\s+|status\s+is\s+)?(?:required|mandatory|necessary|"
        rf"a\s+requirement)\b|\b(?:requires?|requiring)\s+{_US}\s+citizenship\b",
        re.IGNORECASE,
    ),
)
_CITIZEN_IN_LIST_RE = re.compile(
    rf"\b(?:and|,)\s+(?:also\s+)?(?:be\s+)?(?:an?\s+)?{_US}\s+citizens?\b", re.IGNORECASE
)
_MUST_RE = re.compile(r"\b(?:must|required\s+to|need\s+to|needs\s+to|have\s+to)\b", re.I)
_OTHER_STATUS_RE = re.compile(
    r"\b(?:permanent\s+residents?|green[- ]?card|LPRs?|residents?|nationals?|refugees?|asylees?|"
    r"visas?|daca|tps|lawful|either|protected\s+individuals?|authorized\s+to\s+work|"
    r"eligible\s+to\s+work|work\s+authori[sz]ation|opt|cpt)\b",
    re.IGNORECASE,
)
_ALTERNATIVE_AFTER_RE = re.compile(
    r"\s*(?:,\s*)?(?:[-–—]+\s*)?(?:\(\s*)?(?:or|and/or|/|nor)\s+"
    r"(?!older\b|younger\b|over\b|more\b)"
    r"|\s*,?\s+and\s+(?:non\b|international\b|dual\b|foreign\b|other\b|those\b|anyone\b|everyone\b)",
    re.IGNORECASE,
)
_CITIZEN_WORD_RE = re.compile(r"\b(?:citizens?|citizenship)\b", re.IGNORECASE)
# A positive statement that non-citizens may take part: contradicts a "citizens only" clause
# elsewhere in the same posting, so the citizenship proposal is withdrawn.
_CIT_WAIVER_RE = re.compile(
    r"\bnon[-\s]*(?:U\.S\.|US)?[-\s]*citizens?\b|\binternational\s+(?:students?|applicants?|"
    r"candidates?)\b|\bforeign\s+(?:nationals?|students?)\b|\bdual\s+citizens?\b",
    re.IGNORECASE,
)
_WAIVER_POSITIVE_RE = re.compile(r"\b(?:may|can|are|is|also|eligible|welcome|encouraged)\b", re.I)


def _match_citizenship(clause: str) -> list[_Hit]:
    if _OTHER_STATUS_RE.search(clause) or _FOREIGN_COUNTRY_RE.search(clause):
        return []
    if len(_CITIZEN_WORD_RE.findall(clause)) > 1:
        return []  # "U.S. citizen, U.K. citizen, or ..." is a list of nationalities
    patterns = _CITIZENSHIP_PATTERNS
    if _MUST_RE.search(clause):
        patterns = (*patterns, _CITIZEN_IN_LIST_RE)
    for pattern in patterns:
        match = pattern.search(clause)
        if match is None:
            continue
        if _ALTERNATIVE_AFTER_RE.match(clause, match.end()):
            return []
        return [_Hit(RequirementType.CITIZENSHIP, {"countries": ["US"]}, match.start())]
    return []


_PR_TERM = (
    r"(?:(?:lawful\s+|legal\s+)?permanent\s+residents?|LPRs?|green[- ]?card\s+(?:holders?|"
    r"recipients?)|holders?\s+of\s+(?:an?\s+)?green[- ]?card)"
)
_PR_SEP = r"\s*(?:,\s*(?:or\s+|and\s+)?|or|and/or|and|/)\s*"
_CITIZEN_OR_PR_RE = re.compile(
    rf"\b(?:{_US}\s+)?{_CIT}{_PR_SEP}(?:an?\s+)?(?:{_US}\s+)?{_PR_TERM}"
    rf"|\b{_PR_TERM}{_PR_SEP}(?:an?\s+)?{_US}\s+{_CIT}",
    re.IGNORECASE,
)
_PR_EXTRA_STATUS_RE = re.compile(
    r"\b(?:nationals?|refugees?|asylees?|visas?|daca|tps|protected\s+individuals?|"
    r"authorized\s+to\s+work|eligible\s+to\s+work|work\s+authori[sz]ation|either|opt|cpt)\b",
    re.IGNORECASE,
)
_US_MENTION_RE = re.compile(_US, re.IGNORECASE)


def _match_citizen_or_pr(clause: str) -> list[_Hit]:
    match = _CITIZEN_OR_PR_RE.search(clause)
    if (
        match is None
        or _PR_EXTRA_STATUS_RE.search(clause)
        or _FOREIGN_COUNTRY_RE.search(clause)
        or not _US_MENTION_RE.search(clause)
        or not _has_lead(clause, match.start())
    ):
        return []
    return [_Hit(RequirementType.OTHER, {"description": OTHER_CITIZEN_OR_PR_LABEL}, match.start())]


_US_PERSON_RE = re.compile(rf"\b{_US}\s+persons?\b", re.IGNORECASE)
_EXPORT_TERM_RE = re.compile(
    r"\b(?:(?-i:ITAR)|International\s+Traffic\s+in\s+Arms|Export\s+Administration\s+Regulations|"
    r"export[- ]control(?:led|s)?)\b|(?-i:\bEAR\b)",
    re.IGNORECASE,
)
_US_PERSON_LEAD_RE = re.compile(
    r"\b(?:must|required?|requires?|only|eligib\w+|need\s+to|as\s+defined|per|under|"
    r"restricted\s+to|limited\s+to|subject\s+to)\b",
    re.IGNORECASE,
)
# An export-control term alone (no "U.S. person") is a requirement on the candidate only when
# worded as eligibility/status: "requires access to export-controlled data", "must complete export
# control training" and "must comply with ITAR" are not.
_EXPORT_LEAD_RE = re.compile(
    r"\b(?:eligib\w+|only|restricted\s+to|limited\s+to|(?:must|need\s+to|required\s+to)\s+be)\b",
    re.IGNORECASE,
)


# "U.S. person ... or otherwise eligible for deemed export licensing" is an either/or: the posting
# does not require U.S. person status.
_EXPORT_LICENSE_ALT_RE = re.compile(
    r"\bdeemed[- ]exports?\b|\bor\s+(?:otherwise\s+)?(?:be\s+)?eligible\s+for\s+(?:an?\s+)?"
    r"(?:\w+\s+){0,3}?export\s+licen[sc]es?\b",
    re.IGNORECASE,
)


def _match_us_person(clause: str) -> list[_Hit]:
    if _EXPORT_LICENSE_ALT_RE.search(clause):
        return []
    person = _US_PERSON_RE.search(clause)
    if person is not None and _US_PERSON_LEAD_RE.search(clause):
        return [_Hit(RequirementType.OTHER, {"description": OTHER_US_PERSON_LABEL}, person.start())]
    export = _EXPORT_TERM_RE.search(clause)
    if export is not None and _EXPORT_LEAD_RE.search(clause):
        return [_Hit(RequirementType.OTHER, {"description": OTHER_US_PERSON_LABEL}, export.start())]
    return []


_WORK_AUTH_PATTERNS = (
    re.compile(
        rf"\b(?:legally\s+|lawfully\s+)?(?:authorized|eligible|permitted|allowed)\s+to\s+work\s+"
        rf"(?:legally\s+)?(?:in|within)\s+{_US}",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:legal\s+right|authorization)\s+to\s+work\s+in\s+{_US}"
        rf"(?:\s+(?:is\s+)?(?:required|needed|mandatory))?",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:valid\s+|current\s+|legal\s+)?(?:{_US}\s+)?work\s+authori[sz]ation"
        rf"(?:\s+in\s+{_US})?\s+(?:is\s+)?(?:required|needed|mandatory)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:must|need\s+to|required\s+to)\s+(?:have|possess|hold)\s+(?:valid\s+|current\s+|"
        rf"legal\s+)?(?:{_US}\s+)?work\s+authori[sz]ation",
        re.IGNORECASE,
    ),
)
_SPONSOR_OBJECT = (
    r"(?:\s+(?:work\s+|employment\s+|student\s+|any\s+|new\s+)?"
    r"(?:visas?|H-?1B|immigration|applicants?|candidates?|interns?|employees?|"
    r"work\s+authorization)\b(?!['’])|\s*(?:[.,;:)]|$)|\s+(?:now|currently|at\s+this\s+time|"
    r"for\s+this)\b)"
)
_NO_SPONSOR_PATTERNS = (
    re.compile(
        r"\bwithout\s+(?:(?:current|future|now|any|visa|employer|immigration|or|and|"
        r"in\s+the\s+future|at\s+any\s+time)\s+)*sponsorship\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:(?:will|do|does|can|would)\s+not|won't|can't|cannot|don't|doesn't|unable\s+to|"
        r"not\s+able\s+to)\s+(?:currently\s+|now\s+)?(?:sponsor\b"
        + _SPONSOR_OBJECT
        + r"|(?:provide|offer)\s+(?:visa\s+|employment\s+|immigration\s+|work\s+)?sponsorship\b"
        r"(?!\s+(?:opportunit|packages?|tiers?|deals?|for\s+(?:events?|conferences?|hackathons?|"
        r"teams?|clubs?|organi[sz]ations?|nonprofits?)))"
        r")",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bsponsorship\s+(?:is\s+|are\s+|will\s+be\s+)?(?:not\s+(?:available|offered|provided|"
        r"possible)|unavailable)\b|\bno\s+(?:visa\s+|employer\s+|work\s+)?sponsorship\s+"
        r"(?:is\s+|will\s+be\s+)?(?:available|offered|provided|possible)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:must|need\s+to|should)\s+not\s+(?:now\s+or\s+in\s+the\s+future\s+)?require\s+"
        r"(?:(?:current|future|visa|employment|immigration|work)\s+(?:or\s+(?:future\s+)?)?)*"
        r"sponsorship\b|\b(?:who|that)\s+(?:do|does)\s+not\s+(?:now\s+or\s+in\s+the\s+future\s+)?"
        r"require\s+(?:(?:current|future|visa|employment|immigration|work)\s+(?:or\s+)?)*"
        r"sponsorship\b",
        re.IGNORECASE,
    ),
)
_NO_SPONSORSHIP_RE = re.compile("|".join(p.pattern for p in _NO_SPONSOR_PATTERNS), re.IGNORECASE)
_POSITIVE_SPONSOR_RE = re.compile(
    r"\b(?:do|does|will|can|would|are\s+able\s+to)\s+(?:also\s+)?(?:sponsor|provide\s+(?:visa\s+)?"
    r"sponsorship|offer\s+(?:visa\s+)?sponsorship)\b|\bsponsorship\s+(?:is\s+|may\s+be\s+)?"
    r"available\b|\bavailable\s+sponsorship\b",
    re.IGNORECASE,
)


def _match_no_sponsorship(clause: str) -> list[_Hit]:
    """Evaluated BEFORE the generic negation guard: these sentences are negative in form but state
    a positive requirement. Narrow patterns only; "no sponsorship questions" never matches."""
    if _POSITIVE_SPONSOR_RE.search(clause) or _FOREIGN_COUNTRY_RE.search(clause):
        return []
    for pattern in _NO_SPONSOR_PATTERNS:
        match = pattern.search(clause)
        if match is not None:
            return [
                _Hit(
                    RequirementType.WORK_AUTHORIZATION,
                    {"description": WORK_AUTH_NO_SPONSORSHIP_LABEL},
                    match.start(),
                )
            ]
    return []


def _match_work_authorization(clause: str) -> list[_Hit]:
    if _FOREIGN_COUNTRY_RE.search(clause):
        return []
    for pattern in _WORK_AUTH_PATTERNS:
        match = pattern.search(clause)
        if match is not None and _has_lead(clause, match.start()):
            return [
                _Hit(
                    RequirementType.WORK_AUTHORIZATION,
                    {"description": WORK_AUTH_LABEL},
                    match.start(),
                )
            ]
    return []


# --- security clearance ---------------------------------------------------------------------------

_CLEARANCE_KIND = (
    r"(?:(?:interim|final)\s+)?(?:(?:(?:U\.S\.|US|DoD|government|federal)\s+)*"
    r"(?:top\s+secret|secret|ts/sci|ts|sci|public\s+trust|confidential|dod)\s+)?"
)
_CLEARANCE_RE = re.compile(
    r"\b(?:must|need\s+to|required\s+to|have\s+to)\s+(?:currently\s+)?(?:have|hold|possess|"
    r"maintain)\s+(?:an?\s+)?(?:(?:active|current|valid|existing)\s+)?"
    + _CLEARANCE_KIND
    + r"(?:security\s+)?clearance\b"
    r"|\b(?:requires?|requiring)\s+an?\s+(?:(?:active|current|valid)\s+)?"
    + _CLEARANCE_KIND
    + r"(?:security\s+)?clearance\b"
    r"|\b(?:(?:active|current|valid)\s+)?"
    + _CLEARANCE_KIND
    + r"(?:security\s+)?clearance\s+(?:is\s+)?required\b",
    re.IGNORECASE,
)


# "clearance or be eligible to obtain one", "clearance-eligible", "clearance eligibility": an
# alternative or an eligibility statement, not a held clearance.
_CLEARANCE_QUALIFIED_RE = re.compile(
    r"-|\s+(?:eligib\w*|process|paperwork|forms?)\b|\s*(?:,\s*)?(?:or|and/or|/)\s+"
    r"(?!equivalent\b)",
    re.IGNORECASE,
)


def _match_clearance(clause: str) -> list[_Hit]:
    match = _CLEARANCE_RE.search(clause)
    if match is None or _CLEARANCE_QUALIFIED_RE.match(clause, match.end()):
        return []
    return [
        _Hit(RequirementType.OTHER, {"description": OTHER_SECURITY_CLEARANCE_LABEL}, match.start())
    ]


# --- assembly -------------------------------------------------------------------------------------

_MATCHERS = (
    _match_minimum_age,
    _match_education,
    _match_return_to_school,
    _match_graduation,
    _match_standing,
    _match_citizenship,
    _match_citizen_or_pr,
    _match_us_person,
    _match_work_authorization,
    _match_clearance,
)


def _clause_hits(clause: str) -> list[_Hit]:
    if _other_role_only(clause) or _HEDGE_RE.search(clause) or _QUESTION_RE.search(clause):
        return []
    hits = _match_no_sponsorship(clause)  # negative in form, so before the negation guard
    no_sponsorship = bool(hits)
    if no_sponsorship:
        # The "does not sponsor" span is spent; the rest of the clause is still judged on its own
        # ("U.S. Person status is required, and X does not provide visa sponsorship").
        # Blanked at equal length so the remaining hits' positions still index the original clause.
        clause_rest = _NO_SPONSORSHIP_RE.sub(lambda m: " " * len(m.group()), clause)
    else:
        clause_rest = clause
    if _NEGATION_RE.search(_DATE_BOUND_NEGATION_RE.sub(" ", clause_rest)):
        return hits
    for matcher in _MATCHERS:
        if matcher is _match_work_authorization and no_sponsorship:
            continue  # the no-sponsorship label is the more specific statement of the same fact
        hits.extend(matcher(clause_rest))
    return sorted(hits, key=lambda h: h.position)


def _excerpt(clause: str, position: int) -> str:
    """The clause, or a window of at most MAX_EXCERPT_CHARS around the matched phrase, so the
    evidence always shows what the proposal is based on."""
    if len(clause) <= MAX_EXCERPT_CHARS:
        return clause
    # Room for an ellipsis on each cut side; the match starts a third of the way in.
    width = MAX_EXCERPT_CHARS - 2
    start = max(0, min(position - width // 3, len(clause) - width))
    end = start + width
    return ("…" if start else "") + clause[start:end] + ("…" if end < len(clause) else "")


def _valid_value(requirement_type: RequirementType, value: dict[str, Any]) -> dict[str, Any] | None:
    schema = REQUIREMENT_VALUE_SCHEMAS.get(requirement_type)
    if schema is None:
        return value
    try:
        return schema.model_validate(value).model_dump(mode="json")
    except ValidationError:
        return None  # defensive: a matcher produced a shape its own schema rejects


_AGE_WAIVER_RE = re.compile(
    r"\b(?:parental|guardian)\s+(?:consent|permission|approval)\b", re.IGNORECASE
)
_AGE_WAIVER_SCOPE_RE = re.compile(
    r"\b(?:younger|under|below|minors?|or\s+have|or\s+\d+\s+with|with)\b", re.IGNORECASE
)


def _withdraw_contradicted(proposals: list[Proposal], clauses: list[str]) -> list[Proposal]:
    """Posting-level contradictions: "citizens only" next to "non-U.S. citizens may also apply",
    or "must be 18" next to "younger applicants need parental consent", means the stated rule is
    not hard. The proposal is withdrawn (precision over recall)."""
    non_citizens_ok = any(
        _CIT_WAIVER_RE.search(c)
        and _WAIVER_POSITIVE_RE.search(c)
        and not _NEGATION_RE.search(_CIT_WAIVER_RE.sub(" ", c))
        for c in clauses
    )
    waivers = [c for c in clauses if _AGE_WAIVER_RE.search(c) and _AGE_WAIVER_SCOPE_RE.search(c)]

    def age_waived(years: int) -> bool:
        for clause in waivers:
            numbers = [int(n) for n in re.findall(r"\b\d{1,2}\b", clause)]
            if not numbers or max(numbers) >= years:
                return True
        return False

    return [
        p
        for p in proposals
        if not (p.requirement_type is RequirementType.CITIZENSHIP and non_citizens_ok)
        and not (p.requirement_type is RequirementType.MINIMUM_AGE and age_waived(p.value["years"]))
    ]


def extract_requirements(inputs: ExtractionInput) -> tuple[Proposal, ...]:
    """Extract at most `MAX_PROPOSALS` proposals, in document order (title, then description),
    deduped by semantic key (first occurrence wins). Several proposals may come from one clause
    when they are different families. Never raises on malformed input text."""
    proposals: list[Proposal] = []
    seen_keys: set[str] = set()

    texts = [(c, True) for c in _clauses(inputs.title)]
    texts += [(c, False) for c in _clauses(inputs.description)]
    for clause, is_title in texts:
        # A title never "opens with" mandatory wording: the prefix defeats the bare-bullet
        # lead-in, so a title needs explicit wording ("U.S. Citizens Only", "... Required").
        prefix = _TITLE_PREFIX if is_title else ""
        for found in _clause_hits(prefix + clause):
            hit = found._replace(position=max(0, found.position - len(prefix)))
            value = _valid_value(hit.requirement_type, hit.value)
            if value is None:
                continue
            applies_at = hit.applies_at or _applies_at(clause)
            key = semantic_key(hit.requirement_type, value, applies_at, hit.reference_date)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            proposals.append(
                Proposal(
                    requirement_type=hit.requirement_type,
                    value=value,
                    applies_at=applies_at,
                    reference_date=hit.reference_date,
                    source_text=_excerpt(clause, hit.position),
                )
            )
            if len(proposals) == MAX_PROPOSALS:
                break
        if len(proposals) == MAX_PROPOSALS:
            break

    return tuple(_withdraw_contradicted(proposals, [c for c, _ in texts]))
