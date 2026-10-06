"""The single source of fit-scoring configuration (ADR-010 §2).

Every weight, threshold, alias, and stop word lives here. Changing any of them changes results,
so it needs a new SCORING_VERSION and an update to docs/scoring.md.
"""

from typing import Final

from app.enums import RemoteMode, RemotePreference

SCORING_VERSION: Final = "v2"

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
        # v2 (ADR-019), reviewed groups. Kept small and explicit.
        {
            "pcb",
            "printed circuit board",
            "printed circuit boards",
            "pcb design",
            "pcb layout",
            "printed circuit board layout",
            "printed circuit board design",
        },
        {"python", "python3"},
        {"c++", "cpp"},
        {"verilog", "systemverilog", "system verilog"},
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


# --- v2 additions (ADR-019) ---------------------------------------------------------------------

# One-way: a skill (key) is also credited when the posting uses one of these narrower phrases.
# Skills only; the explanation says "related".
RELATED_SKILL_TERMS: Final[dict[str, frozenset[str]]] = {
    "machine learning": frozenset({"deep learning", "neural network", "neural networks"}),
}

# Skills short enough to collide with ordinary words (go-to-market, C-suite, rust-proof).
# They match only with a programming-context word within CONTEXT_WINDOW words, and never when
# the next word is in AMBIGUOUS_NEXT_BLOCK[skill].
AMBIGUOUS_SKILLS: Final = frozenset({"go", "c", "r", "rust"})
CONTEXT_WINDOW: Final = 6
SKILL_CONTEXT_WORDS: Final = frozenset(
    """
    python java rust c++ c# golang programming language languages coding backend kubernetes
    docker linux embedded firmware software microservices api apis sql javascript typescript
    matlab verilog fpga git concurrency developer services systems compiler toolchain drivers
    microcontrollers proficiency proficient familiarity experience knowledge grpc libraries
    """.split()  # noqa: SIM905
)
AMBIGUOUS_NEXT_BLOCK: Final[dict[str, frozenset[str]]] = {
    "go": frozenset(
        "to getter getters with above beyond on live forward ahead through back".split()  # noqa: SIM905
    ),
    "c": frozenset("suite level section corporate".split()),  # noqa: SIM905
    "rust": frozenset(
        "proof resistant free belt inhibitor prevention removal".split()  # noqa: SIM905
    ),
    "r": frozenset(),
}

# Course subject groups: (course names, posting terms). A course whose name is in the first set
# earns the keyword points when any posting term of the group appears in the posting.
SUBJECT_GROUPS: Final[tuple[tuple[frozenset[str], frozenset[str]], ...]] = (
    (
        frozenset(
            {
                "digital logic design",
                "digital logic",
                "logic design",
                "computer architecture",
                "digital design",
                "digital systems",
                "computer organization",
            }
        ),
        frozenset(
            {
                "rtl",
                "fpga",
                "asic",
                "verilog",
                "systemverilog",
                "vhdl",
                "digital design",
                "logic design",
                "microarchitecture",
                "computer architecture",
                "chip",
                "silicon",
                "soc",
            }
        ),
    ),
    (
        frozenset(
            {"circuits i", "circuits ii", "circuit analysis", "electronics", "analog circuits"}
        ),
        frozenset(
            {
                "circuit",
                "circuits",
                "analog",
                "schematic",
                "spice",
                "pcb",
                "printed",
                "hardware",
                "rf",
            }
        ),
    ),
    (
        frozenset({"signals and systems", "digital signal processing", "dsp", "control systems"}),
        frozenset({"signal", "dsp", "wireless", "control", "sensor", "pid", "filters"}),
    ),
    (
        frozenset({"data structures and algorithms", "algorithms", "data structures"}),
        frozenset({"algorithms", "data structures", "software", "backend", "systems"}),
    ),
    (
        frozenset({"linear algebra", "machine learning", "statistics", "probability"}),
        frozenset(
            {
                "machine learning",
                "deep learning",
                "neural",
                "data science",
                "computer vision",
                "models",
            }
        ),
    ),
)

# Location regions. A preferred location that is a region label (or a city inside it) matches a
# posting in any listed city of the same region. Not geocoding; add metros here, deliberately.
REGION_CITIES: Final[dict[str, frozenset[str]]] = {
    "bay area": frozenset(
        {
            "san jose",
            "santa clara",
            "sunnyvale",
            "mountain view",
            "palo alto",
            "san francisco",
            "cupertino",
            "milpitas",
            "fremont",
            "redwood city",
            "menlo park",
            "oakland",
            "san mateo",
            "bay area",
            "silicon valley",
        }
    ),
}
REGION_LABELS: Final = frozenset({"bay area", "silicon valley"})
REGION_CITY_SCORE: Final = 75  # same-region city; a region-label preference scores 100
