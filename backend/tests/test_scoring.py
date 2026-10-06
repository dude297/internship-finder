"""Fit scoring (ADR-010, v2 per ADR-019): pure, deterministic unit tests. All data is synthetic."""

from datetime import UTC, date, datetime

import pytest

from app.enums import RemoteMode, RemotePreference, RequirementsAssessmentStatus
from app.opportunities.scoring import (
    SCORING_VERSION,
    FitOpportunityInput,
    FitProfileInput,
    NamedItem,
    config,
    score_fit,
)
from app.opportunities.scoring.engine import percent
from app.opportunities.scoring.text import Corpus, tokens
from app.repositories import fit_fingerprint

LONG = "x " * 150  # ≥ 200 characters of description


def posting(**changes: object) -> FitOpportunityInput:
    fields: dict[str, object] = {
        "title": "Synthetic Software Intern",
        "organization": "Example Robotics",
        "description": "Work with Python and SQL on synthetic robots.",
    }
    return FitOpportunityInput.model_validate(fields | changes)


def profile(**changes: object) -> FitProfileInput:
    return FitProfileInput.model_validate(changes)


# --- text --------------------------------------------------------------------------------------


def test_tokens_keep_meaningful_punctuation() -> None:
    assert tokens("C++, C#, .NET and Node.js.") == ("c++", "c#", ".net", "and", "node.js")
    assert tokens("Machine-learning / CI/CD") == ("machine", "learning", "ci", "cd")
    assert tokens("ＰＹＴＨＯＮ Straße") == ("python", "strasse")  # NFKC + casefold
    assert tokens(None) == ()


def test_phrase_matching_is_contiguous_and_does_not_cross_fields() -> None:
    corpus = Corpus("Machine Learning Intern", "Learning machine tools.")
    assert corpus.matches(tokens("machine learning"))
    assert not corpus.matches(tokens("intern learning"))  # spans the field boundary
    assert not Corpus("learning about machine").matches(tokens("machine learning"))


def test_aliases_match_both_ways() -> None:
    assert Corpus("Experience with ML models").matches(tokens("Machine Learning"))
    assert Corpus("machine learning").matches(tokens("ml"))
    assert Corpus("JS and TS").matches(tokens("TypeScript"))
    assert Corpus("PostgreSQL").matches(tokens("postgres"))


def test_punctuation_sensitive_terms_do_not_collapse() -> None:
    corpus = Corpus("We use C# and .NET.")
    assert corpus.matches(tokens("C#"))
    assert corpus.matches(tokens(".net"))
    assert corpus.matches(tokens("dotnet"))
    assert not corpus.matches(tokens("C++"))
    assert not corpus.matches(tokens("C"))
    assert not Corpus("C++ required").matches(tokens("C#"))


# --- rounding ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [(1, 8, 13), (1, 3, 33), (2, 3, 67), (1, 2, 50), (5, 8, 63), (0, 4, 0), (4, 4, 100)],
)
def test_percent_rounds_half_up(numerator: int, denominator: int, expected: int) -> None:
    # 1/8 = 12.5 → 13 and 5/8 = 62.5 → 63 (banker's rounding would give 12 and 62).
    assert percent(numerator, denominator) == expected


def test_final_score_rounds_half_up() -> None:
    # technical 50 × 35 = 1750 plus quality 0 → 17.5 → 18.
    result = score_fit(profile(skills=["python", "golang"]), posting(description="python"))
    assert result.components["technical"].score == 50
    assert result.components["quality"].score == 0
    assert result.score == 18


def test_weights_are_the_approved_weights_unchanged_in_v2() -> None:
    assert SCORING_VERSION == "v2"
    assert config.WEIGHTS == {
        "technical": 35,
        "academic": 20,
        "projects": 15,
        "interests": 10,
        "location_schedule": 10,
        "quality": 10,
    }


# --- components --------------------------------------------------------------------------------


def test_technical_matched_and_unmatched() -> None:
    result = score_fit(profile(skills=["Python", "SQL", "Rust", "python", " "]), posting())
    technical = result.components["technical"]
    assert technical.score == 67  # 2 of 3 distinct usable skills
    assert technical.matched == ["Python", "SQL"]
    assert technical.unmatched == ["Rust"]
    assert technical.reason == "Matched 2 of 3 skills: Python, SQL."
    assert not technical.missing


def test_academic_exact_and_keyword_rules() -> None:
    result = score_fit(
        profile(courses=["Data Science", "AP Calculus BC", "Intro to Robotics", "Poetry"]),
        posting(description="Data science and robotics work; calculus helps."),
    )
    academic = result.components["academic"]
    # Data Science exact (2); Intro to Robotics keyword (1); AP Calculus BC needs "bc" too (0).
    assert academic.details == {"exact": ["Data Science"], "keywords": ["Intro to Robotics"]}
    assert academic.unmatched == ["AP Calculus BC", "Poetry"]
    assert academic.score == percent(3, 8)


def test_academic_filler_only_course_needs_an_exact_match() -> None:
    academic = score_fit(profile(courses=["Honors II"]), posting()).components["academic"]
    assert academic.score == 0 and not academic.missing


def test_projects_strongest_item_and_saturation() -> None:
    result = score_fit(
        profile(
            projects=[
                NamedItem(name="Synthetic Garden", description="Watering schedule app"),
                NamedItem(name="Rover", description="Python sensors robots navigation lidar"),
            ],
            research=[NamedItem(name="Synthetic Study", description="Sensors survey")],
        ),
        posting(
            title="Robotics Intern",
            description="Python robots with lidar sensors for navigation mapping.",
        ),
    )
    projects = result.components["projects"]
    assert projects.score == 100  # rover shares 5 keywords
    assert projects.matched == ["Rover", "Synthetic Study"]
    assert projects.details == {
        "items": [
            {"name": "Rover", "keywords": ["python", "sensors", "robots", "navigation", "lidar"]},
            {"name": "Synthetic Study", "keywords": ["sensors"]},
        ]
    }
    assert projects.unmatched == ["Synthetic Garden"]


def test_projects_partial_overlap_and_generic_words_ignored() -> None:
    item = NamedItem(name="Team project", description="Built software using Python and SQL")
    projects = score_fit(profile(projects=[item]), posting()).components["projects"]
    # "team", "project", "built", "using" are generic; python + sql + software? "software" isn't
    # generic but the posting title has it → 3 keywords.
    assert projects.details == {
        "items": [{"name": "Team project", "keywords": ["software", "python", "sql"]}]
    }
    assert projects.score == percent(3, 5)


def test_interests_include_the_organization() -> None:
    interests = score_fit(profile(interests=["robotics", "semiconductors"]), posting()).components[
        "interests"
    ]
    assert interests.matched == ["robotics"]
    assert interests.score == 50


@pytest.mark.parametrize(
    ("preference", "mode", "expected"),
    [
        (RemotePreference.REMOTE_ONLY, RemoteMode.REMOTE, 100),
        (RemotePreference.REMOTE_ONLY, RemoteMode.HYBRID, 50),
        (RemotePreference.REMOTE_ONLY, RemoteMode.ONSITE, 0),
        (RemotePreference.REMOTE_PREFERRED, RemoteMode.ONSITE, 50),
        (RemotePreference.HYBRID_PREFERRED, RemoteMode.HYBRID, 100),
        (RemotePreference.HYBRID_PREFERRED, RemoteMode.REMOTE, 75),
        (RemotePreference.ONSITE_PREFERRED, RemoteMode.REMOTE, 50),
        (RemotePreference.NO_PREFERENCE, RemoteMode.ONSITE, 100),
    ],
)
def test_work_mode_table(preference: RemotePreference, mode: RemoteMode, expected: int) -> None:
    component = score_fit(
        profile(remote_preference=preference), posting(remote_mode=mode)
    ).components["location_schedule"]
    assert component.score == expected


def test_location_is_the_weaker_of_mode_and_place() -> None:
    fit = profile(
        remote_preference=RemotePreference.HYBRID_PREFERRED,
        preferred_locations=["San Jose, CA", "Santa Clara"],
    )
    hit = score_fit(fit, posting(remote_mode=RemoteMode.HYBRID, location="San Jose, California"))
    assert hit.components["location_schedule"].score == 100
    assert "Location matches San Jose, CA." in hit.components["location_schedule"].reason
    miss = score_fit(fit, posting(remote_mode=RemoteMode.HYBRID, location="Example City"))
    assert miss.components["location_schedule"].score == 0
    # Remote postings don't need a matching location.
    remote = score_fit(fit, posting(remote_mode=RemoteMode.REMOTE, location="Example City"))
    assert remote.components["location_schedule"].score == 75


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2041, 6, 20), date(2041, 8, 1), 100),  # inside
        (date(2041, 6, 1), date(2041, 7, 1), 50),  # partial overlap
        (date(2041, 9, 1), date(2041, 12, 1), 0),  # no overlap
        (date(2041, 7, 1), None, 50),  # starts inside, end unknown
        (date(2041, 1, 1), None, 0),  # starts outside
    ],
)
def test_schedule_rules(start: date, end: date | None, expected: int) -> None:
    fit = profile(availability_start=date(2041, 6, 15), availability_end=date(2041, 8, 31))
    component = score_fit(fit, posting(start_date=start, end_date=end)).components[
        "location_schedule"
    ]
    assert component.score == expected
    assert not component.missing


def test_location_and_schedule_average_half_up() -> None:
    fit = profile(
        remote_preference=RemotePreference.REMOTE_PREFERRED,
        availability_start=date(2041, 6, 15),
    )
    # place 75 (hybrid), schedule 50 (starts inside, end unknown) → 62.5 → 63
    component = score_fit(
        fit, posting(remote_mode=RemoteMode.HYBRID, start_date=date(2041, 7, 1))
    ).components["location_schedule"]
    assert component.score == 63


def test_location_schedule_unknown_posting_data_is_missing_not_matched() -> None:
    fit = profile(availability_start=date(2041, 6, 15))
    component = score_fit(fit, posting()).components["location_schedule"]
    assert component.missing and component.missing_input == "opportunity"
    assert component.score == 0


def test_quality_points() -> None:
    full = posting(
        description=LONG,
        application_url="https://example.org/apply",
        application_deadline=date(2041, 2, 1),
        start_date=date(2041, 6, 20),
        posted_at=datetime(2040, 9, 1, tzinfo=UTC),
        requirements_assessment_status=RequirementsAssessmentStatus.PARTIAL,
    )
    assert score_fit(profile(), full).components["quality"].score == 100
    empty = score_fit(profile(), posting(description="short")).components["quality"]
    assert empty.score == 0
    assert "Missing a detailed description" in empty.reason
    unassessed = full.model_copy(
        update={"requirements_assessment_status": RequirementsAssessmentStatus.UNASSESSED}
    )
    assert score_fit(profile(), unassessed).components["quality"].score == 90


# --- missing data, coverage, boundaries --------------------------------------------------------


def test_empty_profile_scores_only_quality_with_coverage_10() -> None:
    result = score_fit(profile(), posting(description=LONG))
    assert result.coverage == 10
    for key in ("technical", "academic", "projects", "interests", "location_schedule"):
        component = result.components[key]
        assert component.missing and component.score == 0
        assert component.missing_input == "profile"
    assert result.score == 3  # quality 25 × 10 / 100 = 2.5 → 3


def test_perfect_and_zero_boundaries() -> None:
    fit = profile(
        skills=["Python"],
        courses=["Data Science"],
        projects=[NamedItem(name="Rover", description="python sql data science robots")],
        interests=["robotics"],
        remote_preference=RemotePreference.NO_PREFERENCE,
    )
    best = posting(
        description="Python, SQL, data science, robots, rover. " + LONG,
        remote_mode=RemoteMode.ONSITE,
        application_url="https://example.org/apply",
        application_deadline=date(2041, 2, 1),
        start_date=date(2041, 6, 20),
        posted_at=datetime(2040, 9, 1, tzinfo=UTC),
        requirements_assessment_status=RequirementsAssessmentStatus.COMPLETE,
    )
    result = score_fit(fit, best)
    assert result.score == 100 and result.coverage == 100
    worst = score_fit(
        profile(skills=["Fortran"], remote_preference=RemotePreference.REMOTE_ONLY),
        posting(title="Synthetic Clerk", description="Filing.", remote_mode=RemoteMode.ONSITE),
    )
    assert worst.score == 0
    assert worst.coverage == 35 + 10 + 10


def test_deterministic_and_serializable() -> None:
    fit = profile(skills=["Python"], interests=["robots"])
    first = score_fit(fit, posting()).model_dump(mode="json")
    assert first == score_fit(fit, posting()).model_dump(mode="json")
    assert first["scoring_version"] == "v2"
    assert set(first["components"]) == set(config.WEIGHTS)


# --- fit fingerprint (ADR-010 §8) ---------------------------------------------------------------


class _Row:
    """Stands in for an ORM opportunity: fit reads only its fit fields."""

    def __init__(self, **fields: object) -> None:
        self.__dict__.update(
            {
                "title": "Synthetic Software Intern",
                "organization": "Example Robotics",
                "description": "Python.",
                "updated_at": datetime(2040, 9, 1, tzinfo=UTC),
                "last_seen_at": datetime(2040, 9, 1, tzinfo=UTC),
                "id": "row-1",
            }
            | fields
        )


def fingerprint(row: _Row, fit: FitProfileInput | None = None) -> str:
    return fit_fingerprint(
        fit or profile(skills=["Python"]), FitOpportunityInput.model_validate(row)
    )


def test_fit_fingerprint_is_stable_and_ignores_bookkeeping() -> None:
    base = fingerprint(_Row())
    assert base == fingerprint(_Row())
    assert len(base) == 64
    moved = _Row(
        updated_at=datetime(2041, 1, 1, tzinfo=UTC),
        last_seen_at=datetime(2041, 1, 1, tzinfo=UTC),
        id="row-2",
    )
    assert fingerprint(moved) == base


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "Renamed"},
        {"organization": "Example Institute"},
        {"description": "SQL."},
        {"location": "Example City"},
        {"remote_mode": RemoteMode.REMOTE},
        {"application_deadline": date(2041, 2, 1)},
        {"start_date": date(2041, 6, 20)},
        {"end_date": date(2041, 8, 1)},
        {"posted_at": datetime(2040, 9, 1, tzinfo=UTC)},
        {"application_url": "https://example.org/apply"},
        {"requirements_assessment_status": RequirementsAssessmentStatus.COMPLETE},
    ],
)
def test_fit_fingerprint_changes_with_each_fit_input(changes: dict[str, object]) -> None:
    assert fingerprint(_Row(**changes)) != fingerprint(_Row())


def test_fit_fingerprint_changes_with_the_profile() -> None:
    base = fingerprint(_Row())
    assert fingerprint(_Row(), profile(skills=["SQL"])) != base
    assert fingerprint(_Row(), profile(skills=["Python"], interests=["robots"])) != base
    assert (
        fingerprint(_Row(), profile(skills=["Python"], availability_end=date(2041, 8, 1))) != base
    )
