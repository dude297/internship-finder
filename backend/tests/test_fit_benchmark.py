"""Fit scoring v2 (ADR-019): synthetic ranking benchmark and per-rule unit tests.

All data is fictional (tests/fit_benchmark_v2.py). The v1 numbers below were measured by running
the same benchmark against the v1 scorer at origin/main e424550.
"""

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.enums import RemoteMode, RemotePreference
from app.opportunities.scoring import (
    SCORING_VERSION,
    FitOpportunityInput,
    FitProfileInput,
    ScoreBreakdown,
    score_fit,
)
from app.opportunities.scoring.text import Corpus, tokens
from tests.fit_benchmark_v2 import EE_PROFILE, POSTINGS, SW_LABELS, SW_PROFILE, Posting

NOW = datetime(2026, 10, 6, tzinfo=UTC)
TRAP_SKILLS = {"Go", "C", "Rust"}

# Measured with the v1 scorer on this benchmark.
V1_EE_NDCG = 0.826
V1_SW_NDCG = 0.708
V1_SW_P10 = 0.60


def _score(profile: FitProfileInput, posting: Posting) -> ScoreBreakdown:
    return score_fit(
        profile,
        FitOpportunityInput.model_validate(
            {
                "title": posting.title,
                "organization": posting.organization,
                "description": posting.description,
                "location": posting.location,
                "remote_mode": posting.mode,
                "application_url": "https://example.test/apply",
                "application_deadline": (NOW + timedelta(days=30)).date(),
                "start_date": date(2027, 6, 1),
                "posted_at": NOW - timedelta(days=posting.age),
            }
        ),
    )


def rank(profile: dict[str, object], labels: list[int]) -> list[tuple[int, int, ScoreBreakdown]]:
    """(posting index, label, breakdown), best first; ties keep benchmark order."""
    fit = FitProfileInput.model_validate(profile)
    rows = [(i, labels[i], _score(fit, p)) for i, p in enumerate(POSTINGS)]
    return sorted(rows, key=lambda r: (-r[2].score, r[0]))


def ndcg_at_10(order: list[tuple[int, int, ScoreBreakdown]], labels: list[int]) -> float:
    def dcg(values: list[int]) -> float:
        return sum((2**v - 1) / math.log2(n + 2) for n, v in enumerate(values[:10]))

    return dcg([label for _, label, _ in order]) / dcg(sorted(labels, reverse=True))


def precision_at_10(order: list[tuple[int, int, ScoreBreakdown]]) -> float:
    return sum(label >= 2 for _, label, _ in order[:10]) / 10


EE_LABELS = [p.label for p in POSTINGS]
SW_LABEL_LIST = [SW_LABELS.get(p.title, 0) for p in POSTINGS]


def test_version_is_v2() -> None:
    assert SCORING_VERSION == "v2"


def test_ee_profile_floors() -> None:
    order = rank(EE_PROFILE, EE_LABELS)
    ndcg = ndcg_at_10(order, EE_LABELS)
    strong_outside_top_20 = sum(label == 3 for _, label, _ in order[20:])
    trap_false_evidence = [
        POSTINGS[i].title
        for i, _, b in order
        if POSTINGS[i].tag.startswith("trap")
        and TRAP_SKILLS & set(b.components["technical"].matched)
    ]
    print(f"EE v2 NDCG@10={ndcg:.3f} P@10={precision_at_10(order):.2f}")
    assert ndcg >= 0.84  # measured 0.865 after the review fixes, minus a small margin
    assert trap_false_evidence == []
    assert strong_outside_top_20 <= 3
    assert ndcg > V1_EE_NDCG


def test_software_profile_is_not_worse_than_v1() -> None:
    """Overfitting guard: the tables were written against the EE profile."""
    order = rank(SW_PROFILE, SW_LABEL_LIST)
    ndcg = ndcg_at_10(order, SW_LABEL_LIST)
    print(f"SW v2 NDCG@10={ndcg:.3f} P@10={precision_at_10(order):.2f}")
    assert ndcg >= V1_SW_NDCG - 0.03
    assert precision_at_10(order) >= V1_SW_P10 - 0.1


# --- A. ambiguous-skill guard ------------------------------------------------------------------

TRUE_MENTIONS = [
    ("Go", "Backend services written in Go, using Kubernetes."),
    ("Go", "We use Go and gRPC."),
    ("Go", "Experience with Go."),
    ("Go", "Go, Python, or Rust."),
    ("C", "Proficiency in C is a must."),
    ("C", "Firmware written in C and C++."),
    ("C", "Strong C programming skills."),
    ("Rust", "Compiler toolchain written in Rust."),
    ("Rust", "Low level compiler work in C and Rust."),
    ("C", "Low level compiler work in C and Rust."),
    # Skill lists without context words (real-looking snippets).
    ("Go", "Requirements\n- Go\n- Terraform\n- Postgres"),
    ("Go", "Tech stack: Go, AWS, Terraform"),
    ("R", "Tools: R, Tableau, Excel"),
    ("R", "Skills: R, Stata, Tableau"),
    ("R", "Data analysis in R or SAS"),
    ("Go", "Python or Go"),
    ("R", "Statistics with R and Python."),
    ("R", "Knowledge of R libraries."),
]
FALSE_MENTIONS = [
    ("Go", "Our go-to-market team plans launches."),
    ("Go", "Go to market experience is a plus."),
    ("Go", "A go-getter attitude."),
    ("Go", "Plan to go above and beyond."),
    ("Go", "Ability to go on site daily."),
    ("C", "Support the C-suite and board."),
    ("C", "Meet C-level leaders."),
    ("Rust", "Rust-proof coating inspection."),
    ("Rust", "Rust resistant gear provided."),
    ("C", "Vitamin C and fruit."),
    ("R", "Join our R&D team."),
    ("R", "Experience in R&D and product."),
    ("R", "R&D intern working in Python on the backend."),
    ("C", "Series C software startup."),
    ("Go", "We go build software systems as a team."),
    ("Go", "Let's go! Software intern."),
    ("Go", "Hiring now: Go, getter, and fast learner."),
]


@pytest.mark.parametrize(("skill", "text"), TRUE_MENTIONS)
def test_guard_keeps_true_mentions(skill: str, text: str) -> None:
    assert Corpus(text).match_via(tokens(skill), skill=True) is not None


@pytest.mark.parametrize(("skill", "text"), FALSE_MENTIONS)
def test_guard_rejects_ordinary_words(skill: str, text: str) -> None:
    assert Corpus(text).match_via(tokens(skill), skill=True) is None


def test_golang_alias_covers_go_but_keeps_the_guard() -> None:
    assert Corpus("Backend services in Golang.").match_via(tokens("Go"), skill=True) == (
        "alias",
        ("golang",),
    )
    assert Corpus("Experience with Go, Python.").match_via(tokens("Golang"), skill=True) is not None
    assert Corpus("Our go-to-market plan.").match_via(tokens("Golang"), skill=True) is None


def test_guard_applies_to_skills_only() -> None:
    # An interest called "go" or a plain phrase match is unchanged (v1 behaviour).
    assert Corpus("go-to-market").matches(tokens("go"))


# --- B. reviewed aliases -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("SystemVerilog", "Verilog"),
        ("PCB design", "printed circuit board layout"),
        ("PCB", "printed circuit boards"),
        ("python3", "Python"),
        ("cpp", "C++"),
    ],
)
def test_reviewed_aliases_match_both_ways(a: str, b: str) -> None:
    assert Corpus(f"Experience with {a}.").matches(tokens(b))
    assert Corpus(f"Experience with {b}.").matches(tokens(a))


def test_related_deep_learning_is_one_way_and_explained() -> None:
    fit = FitProfileInput.model_validate({"skills": ["Machine Learning"]})
    opp = FitOpportunityInput.model_validate(
        {"title": "Intern", "organization": "Example", "description": "Build deep learning models."}
    )
    technical = score_fit(fit, opp).components["technical"]
    assert technical.matched == ["Machine Learning"]
    assert technical.details == {"evidence": {"Machine Learning": "related deep learning"}}
    assert "Machine Learning (related deep learning)" in technical.reason
    reverse = score_fit(
        FitProfileInput.model_validate({"skills": ["Deep Learning"]}),
        opp.model_copy(update={"description": "Machine learning."}),
    )
    assert reverse.components["technical"].matched == []


def test_alias_evidence_is_explained() -> None:
    fit = FitProfileInput.model_validate({"skills": ["Verilog"]})
    opp = FitOpportunityInput.model_validate(
        {"title": "Intern", "organization": "Example", "description": "Write SystemVerilog."}
    )
    technical = score_fit(fit, opp).components["technical"]
    assert technical.details == {"evidence": {"Verilog": "alias systemverilog"}}
    assert "Verilog (alias systemverilog)" in technical.reason


# --- C. course subject groups ------------------------------------------------------------------


def _academic(courses: list[str], description: str):  # noqa: ANN202
    fit = FitProfileInput.model_validate({"courses": courses})
    opp = FitOpportunityInput.model_validate(
        {"title": "Intern", "organization": "Example", "description": description}
    )
    return score_fit(fit, opp).components["academic"]


@pytest.mark.parametrize(
    ("course", "description", "term"),
    [
        ("Digital Logic Design", "Design RTL for an ASIC.", "asic"),
        ("Computer Architecture", "Prototype on FPGA boards.", "fpga"),
        ("Circuits I", "Review the schematic and run SPICE.", "schematic"),
        ("Signals and Systems", "Signal processing for wireless links.", "signal processing"),
        ("Data Structures and Algorithms", "Algorithms for routing.", "algorithms"),
        ("Linear Algebra", "Computer vision research.", "computer vision"),
    ],
)
def test_course_group_connects_course_to_posting(course: str, description: str, term: str) -> None:
    academic = _academic([course], description)
    assert academic.matched == [course]
    assert academic.details is not None
    assert academic.details["groups"] == {course: term}
    assert "course group" in academic.reason and course in academic.reason
    assert academic.score == 50  # keyword points: 1 of 2


@pytest.mark.parametrize(
    "description",
    [
        "Build software systems with a strong backend team and control models.",
        "Hardware and silicon chip packaging, SoC marketing.",
    ],
)
def test_course_groups_ignore_generic_posting_words(description: str) -> None:
    for course in (
        "Digital Logic Design",
        "Signals and Systems",
        "Data Structures and Algorithms",
        "Linear Algebra",
        "Circuits I",
    ):
        assert _academic([course], description).matched == []


def test_course_group_needs_a_posting_term_and_a_listed_course() -> None:
    assert _academic(["Digital Logic Design"], "Write marketing copy.").matched == []
    assert _academic(["Poetry"], "Design RTL for an ASIC.").matched == []
    exact = _academic(["Digital Logic Design"], "We expect digital logic design coursework.")
    assert exact.details == {"exact": ["Digital Logic Design"], "keywords": []}  # no group note


# --- D. locations ------------------------------------------------------------------------------


def _location(preferred: list[str], location: str, mode: RemoteMode | None):  # noqa: ANN202
    fit = FitProfileInput.model_validate(
        {
            "preferred_locations": preferred,
            "remote_preference": RemotePreference.NO_PREFERENCE,
        }
    )
    opp = FitOpportunityInput.model_validate(
        {"title": "Intern", "organization": "Example", "location": location, "remote_mode": mode}
    )
    return score_fit(fit, opp).components["location_schedule"]


def test_region_label_preference_matches_any_city_in_region() -> None:
    component = _location(["Bay Area"], "Sunnyvale, CA", RemoteMode.ONSITE)
    assert component.score == 100
    assert 'Region match: "Sunnyvale, CA" is in the bay area region.' in component.reason


def test_same_region_city_scores_less_than_exact_city() -> None:
    assert _location(["San Jose, CA"], "San Jose, California", RemoteMode.ONSITE).score == 100
    component = _location(["San Jose, CA"], "Santa Clara, CA", RemoteMode.ONSITE)
    assert component.score == 75
    assert "Region match" in component.reason


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("San Jose, Costa Rica", 0),
        ("Oakland, NY", 0),
        ("Fremont, NE", 0),
        ("Santa Clara, CA", 100),
        ("South San Francisco, CA", 100),
        ("Berkeley, California", 100),
        ("San Francisco Bay Area", 100),
    ],
)
def test_region_rejects_other_states_and_countries(location: str, expected: int) -> None:
    assert _location(["Bay Area"], location, RemoteMode.ONSITE).score == expected
    if "San Jose" not in location:  # an exact city text match is the v1 rule, unchanged
        city = _location(["San Jose, CA"], location, RemoteMode.ONSITE).score
        assert city == (75 if expected else 0)


@pytest.mark.parametrize(
    ("location", "remote"),
    [
        ("Remote", True),
        ("Remote - US", True),
        ("Remote (US)", True),
        ("Remote, United States", True),
        ("Remote - Texas", True),
        ("Remote - CA", True),
        ("Remote - Canada", False),
        ("Remote - UK", False),
        ("Not remote, office in Austin", False),
        ("Remote first, office in Boston", False),
        ("Remote - New York City office", False),
        ("No remote work", False),
        ("Austin, TX (Remote)", False),
    ],
)
def test_remote_from_text_is_strict(location: str, remote: bool) -> None:
    score = _location(["San Jose, CA"], location, None).score
    assert score == (100 if remote else 0)


def test_remote_text_never_reaches_eligibility() -> None:
    import app.opportunities.eligibility as eligibility

    assert not hasattr(eligibility, "_remote_in_text")
    source = Path(eligibility.__file__).read_text(encoding="utf-8")
    assert "scoring" not in source.replace("Fit scoring is separate", "")


def test_region_does_not_leak_outside_the_table() -> None:
    assert _location(["Bay Area"], "Austin, TX", RemoteMode.ONSITE).score == 0
    assert _location(["Austin, TX"], "Santa Clara, CA", RemoteMode.ONSITE).score == 0


def test_remote_text_is_remote_when_mode_is_unknown() -> None:
    component = _location(["San Jose, CA"], "Remote - US", None)
    assert component.score == 100
    assert "treated as remote" in component.reason
    # A known mode is never overridden, and non-remote text stays unknown.
    assert _location(["San Jose, CA"], "Remote - US", RemoteMode.ONSITE).score == 0
    assert _location(["San Jose, CA"], "Austin, TX", None).score == 0
