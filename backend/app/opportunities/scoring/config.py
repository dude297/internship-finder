"""The single source of fit-scoring configuration (ADR-010 §2).

Every weight, threshold, alias, and stop word lives here. Changing any of them changes results,
so it needs a new SCORING_VERSION and an update to docs/scoring.md.
"""

from typing import Final

from app.enums import RemoteMode, RemotePreference

SCORING_VERSION: Final = "v1"

# Component key → weight. Weights sum to 100.
WEIGHTS: Final[dict[str, int]] = {
    "technical": 35,
    "academic": 20,
    "projects": 15,
    "interests": 10,
    "location_schedule": 10,
    "quality": 10,
}
assert sum(WEIGHTS.values()) == 100

# Equivalent spellings. Each group's terms are written the way the tokenizer produces them.
ALIAS_GROUPS: Final[tuple[frozenset[str], ...]] = tuple(
    frozenset(group)
    for group in (
        {"javascript", "js"},
        {"typescript", "ts"},
        {"machine learning", "ml"},
        {"artificial intelligence", "ai"},
        {"postgresql", "postgres"},
        {"kubernetes", "k8s"},
        {"natural language processing", "nlp"},
        {"amazon web services", "aws"},
        {"react", "reactjs", "react.js"},
        {"node.js", "nodejs"},
        {".net", "dotnet"},
        {"golang", "go lang"},
    )
)

# Common English words that carry no matching signal.
STOP_WORDS: Final = frozenset(
    """
    a about above after again all also an and any are as at be because been before being below
    between both but by can could did do does doing down during each etc few for from further
    had has have having he her here hers him his how i if in into is it its itself just me more
    most my no nor not now of off on once only or other our ours out over own per same she
    should so some such than that the their theirs them then there these they this those
    through to too under until up very via was we were what when where which while who whom
    why will with within without would you your yours
    """.split()  # noqa: SIM905 -- a readable block
)

# Words too generic to show that a project matches a posting (projects/research only).
GENERIC_WORDS: Final = frozenset(
    """
    ability able build building built candidate candidates company create created day develop
    developed developing development experience experiences good great help helped including
    join knowledge make made new opportunity opportunities people project projects role skill
    skills strong team teams use used using work worked working world year years
    """.split()  # noqa: SIM905
)

# Words that describe a course's level, not its subject (academic keyword rule).
COURSE_FILLER: Final = frozenset(
    """
    advanced ap basic basics course fundamentals honors i ib ii iii intro introduction
    introductory iv level principles seminar topics v
    """.split()  # noqa: SIM905
)

# Projects/research: this many distinct matching keywords earns the full component score.
PROJECT_KEYWORDS_FOR_FULL_SCORE: Final = 5
# How many of the strongest projects/research items the breakdown lists.
PROJECT_ITEMS_SHOWN: Final = 3

# Academic points per course.
COURSE_EXACT_POINTS: Final = 2
COURSE_KEYWORD_POINTS: Final = 1

# Work-mode sub-score: preference → posting mode → 0-100.
WORK_MODE_SCORES: Final[dict[RemotePreference, dict[RemoteMode, int]]] = {
    RemotePreference.REMOTE_ONLY: {
        RemoteMode.REMOTE: 100,
        RemoteMode.HYBRID: 50,
        RemoteMode.ONSITE: 0,
    },
    RemotePreference.REMOTE_PREFERRED: {
        RemoteMode.REMOTE: 100,
        RemoteMode.HYBRID: 75,
        RemoteMode.ONSITE: 50,
    },
    RemotePreference.HYBRID_PREFERRED: {
        RemoteMode.REMOTE: 75,
        RemoteMode.HYBRID: 100,
        RemoteMode.ONSITE: 75,
    },
    RemotePreference.ONSITE_PREFERRED: {
        RemoteMode.REMOTE: 50,
        RemoteMode.HYBRID: 75,
        RemoteMode.ONSITE: 100,
    },
    RemotePreference.NO_PREFERENCE: {
        RemoteMode.REMOTE: 100,
        RemoteMode.HYBRID: 100,
        RemoteMode.ONSITE: 100,
    },
}
LOCATION_MATCH_SCORE: Final = 100
SCHEDULE_INSIDE_SCORE: Final = 100
SCHEDULE_PARTIAL_SCORE: Final = 50  # partial overlap, or only the start date is known and inside

# Opportunity quality: points per completeness signal (sum 100).
MIN_DESCRIPTION_CHARS: Final = 200
QUALITY_POINTS: Final[dict[str, int]] = {
    "description": 25,
    "application_url": 20,
    "application_deadline": 20,
    "start_date": 15,
    "posted_at": 10,
    "requirements_reviewed": 10,
}
assert sum(QUALITY_POINTS.values()) == 100
