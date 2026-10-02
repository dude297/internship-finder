"""`requirements-rules` v1 (ADR-012 §5). Pure; no database. Precision over recall: every case
here either asserts a specific proposal or asserts none."""

import pytest

from app.enums import RequirementAppliesAt, RequirementType
from app.opportunities.requirements.extractor import (
    EXTRACTOR_NAME,
    EXTRACTOR_VERSION,
    MAX_EXCERPT_CHARS,
    MAX_PROPOSALS,
    Proposal,
    extract_requirements,
)
from app.opportunities.requirements.identity import ExtractionInput, semantic_key


def extract(description: str | None, title: str = "Synthetic Internship") -> tuple[Proposal, ...]:
    return extract_requirements(ExtractionInput(title=title, description=description))


def test_extractor_identity() -> None:
    assert EXTRACTOR_NAME == "requirements-rules"
    assert EXTRACTOR_VERSION == "1"


# --- minimum_age ----------------------------------------------------------------------------


def test_welcoming_all_ages_proposes_nothing() -> None:
    assert extract("We welcome applicants of all ages.") == ()


def test_vague_age_statistic_proposes_nothing() -> None:
    assert extract("Most interns are 18.") == ()


def test_must_be_at_least_proposes_minimum_age() -> None:
    (proposal,) = extract("You must be at least 18.")
    assert proposal.requirement_type is RequirementType.MINIMUM_AGE
    assert proposal.value == {"years": 18}
    assert proposal.applies_at is RequirementAppliesAt.PROGRAM_START


def _key(proposal: Proposal) -> str:
    return semantic_key(
        proposal.requirement_type, proposal.value, proposal.applies_at, proposal.reference_date
    )


def test_rephrased_minimum_age_shares_semantic_key() -> None:
    (a,) = extract("Applicants must be at least 16 years old.")
    (b,) = extract("Minimum age: 16.")
    assert a.value == b.value == {"years": 16}
    assert _key(a) == _key(b)


def test_out_of_range_ages_propose_nothing() -> None:
    for age in (5, 99, 150):
        assert extract(f"You must be at least {age} years old.") == ()


def test_applies_at_application_phrase() -> None:
    (proposal,) = extract("You must be at least 18 at the time of application.")
    assert proposal.applies_at is RequirementAppliesAt.APPLICATION


# --- citizenship ------------------------------------------------------------------------------


def test_citizenship_preferred_proposes_nothing() -> None:
    assert extract("U.S. citizenship is preferred.") == ()


def test_citizenship_required_proposes_citizenship() -> None:
    (proposal,) = extract("U.S. citizenship required.")
    assert proposal.requirement_type is RequirementType.CITIZENSHIP
    assert proposal.value == {"countries": ["US"]}


def test_must_be_a_us_citizen_proposes_citizenship() -> None:
    (proposal,) = extract("Must be a U.S. citizen.")
    assert proposal.value == {"countries": ["US"]}


def test_citizen_or_permanent_resident_is_work_authorization_not_citizenship() -> None:
    (proposal,) = extract("Must be a citizen or permanent resident.")
    assert proposal.requirement_type is RequirementType.WORK_AUTHORIZATION


def test_citizen_or_alternative_status_is_never_citizenship() -> None:
    for text in (
        "Must be a U.S. citizen or green card holder.",
        "Applicants must be U.S. citizens or permanent residents.",
        "Must be a U.S. citizen or lawful permanent resident.",
        "U.S. citizens only, or nationals of partner countries.",
    ):
        assert all(p.requirement_type is not RequirementType.CITIZENSHIP for p in extract(text))
    (proposal,) = extract("Applicants must be U.S. citizens or permanent residents.")
    assert proposal.requirement_type is RequirementType.WORK_AUTHORIZATION


def test_completed_education_level_is_not_enrollment() -> None:
    for text in (
        "Must be a graduate of an accredited program.",
        "Must be a high school graduate.",
        "Must be a high school diploma holder.",
    ):
        assert extract(text) == (), text
    (proposal,) = extract("Must be a graduate student.")
    assert proposal.value == {"levels": ["graduate"], "accepts_incoming": False}
    (proposal,) = extract("Applicants must be currently enrolled in high school.")
    assert proposal.value == {"levels": ["high_school"], "accepts_incoming": False}


def test_us_person_proposes_nothing() -> None:
    assert extract("Applicants should be a U.S. person.") == ()


def test_work_authorization_required() -> None:
    (proposal,) = extract("Must be authorized to work in the United States.")
    assert proposal.requirement_type is RequirementType.WORK_AUTHORIZATION
    assert proposal.value == {"description": "Authorized to work in the United States"}


# --- education --------------------------------------------------------------------------------


def test_college_experience_preferred_proposes_nothing() -> None:
    assert extract("College experience preferred.") == ()


def test_currently_enrolled_undergraduate_only() -> None:
    (proposal,) = extract("Currently enrolled undergraduate students only.")
    assert proposal.requirement_type is RequirementType.EDUCATION
    assert proposal.value == {"levels": ["undergraduate"], "accepts_incoming": False}


def test_must_be_high_school_student() -> None:
    (proposal,) = extract("Must be a high school student.")
    assert proposal.value == {"levels": ["high_school"], "accepts_incoming": False}


def test_currently_enrolled_in_high_school() -> None:
    (proposal,) = extract("Currently enrolled in high school.")
    assert proposal.value == {"levels": ["high_school"], "accepts_incoming": False}


def test_must_be_enrolled_in_graduate_program() -> None:
    (proposal,) = extract("Must be enrolled in a graduate program.")
    assert proposal.value == {"levels": ["graduate"], "accepts_incoming": False}


def test_rising_high_school_senior_never_undergraduate() -> None:
    assert extract("Open to rising seniors in high school.") == ()
    assert extract("She is a high school senior.") == ()


def test_explicit_incoming_undergraduate_language() -> None:
    (proposal,) = extract("Open to incoming undergraduate students.")
    assert proposal.value == {"levels": ["undergraduate"], "accepts_incoming": True}


# --- soft skills and vague audiences -----------------------------------------------------------


def test_soft_skills_and_vague_audiences_propose_nothing() -> None:
    for sentence in (
        "strong communication skills",
        "team player",
        "passion for technology",
        "Open to teens.",
        "Open to young people.",
        "high-school age applicants welcome.",
    ):
        assert extract(sentence) == ()


# --- determinism, bounds, robustness -----------------------------------------------------------


def test_determinism() -> None:
    description = "Must be at least 18. Must be a U.S. citizen. Must be a high school student."
    assert extract(description) == extract(description)


def test_cap_at_twenty_proposals() -> None:
    sentences = " ".join(f"Must be at least {age} years of age or older." for age in range(10, 31))
    proposals = extract(sentences)
    assert len(proposals) == MAX_PROPOSALS


def test_source_text_excerpt_is_bounded() -> None:
    long_sentence = "Must be at least 18 years of age or older"
    long_sentence += " and also a very long clause" * 20
    (proposal,) = extract(long_sentence + ".")
    assert len(proposal.source_text) <= MAX_EXCERPT_CHARS


def test_html_ish_and_odd_unicode_input_does_not_crash() -> None:
    assert extract("<p>Must be at least 18.</p>   café \U0001f600") != ()
    assert extract("<<<>>> ??? !!! \x00\x01") == ()


def test_none_description_works() -> None:
    assert extract(None) == ()


def test_dedupes_rephrased_duplicate_within_one_posting() -> None:
    description = "Must be at least 16 years old. Minimum age: 16."
    proposals = extract(description)
    assert len(proposals) == 1


# --- Adversarial review findings (2026-10-02) -------------------------------------------------

CONTRADICTING_OR_NON_REQUIREMENTS = (
    # citizenship alternatives (the U.S. abbreviation must not hide them)
    "Must be a U.S. citizen or U.S. permanent resident.",
    "Must be a U.S. citizen or U.S. national.",
    "Must be a U.S. citizen, permanent resident, or DACA recipient.",
    "Non-U.S. citizens only may apply.",
    # numbers that aren't minimum ages
    "Applicants must be 18 years of age or younger.",
    "Students must be at least 18 months into their degree.",
    "You must be available at least 20 hours per week.",
    "Must be at least 16 weeks long.",
    # negations
    "No security clearance is required.",
    "You do not need a security clearance.",
    "You do not need to be authorized to work in the United States.",
    "Applicants currently enrolled in a graduate program are not eligible.",
    "You must not be currently enrolled in high school.",
    # a list of alternative levels
    "Must be a high school student, undergraduate, or graduate student.",
)


@pytest.mark.parametrize("text", CONTRADICTING_OR_NON_REQUIREMENTS)
def test_never_proposes_a_requirement_the_text_contradicts(text: str) -> None:
    assert extract(text) == ()


def test_age_followed_by_a_date_phrase_still_counts() -> None:
    (proposal,) = extract("Must be at least 16 by June 1.")
    assert proposal.value == {"years": 16}


def test_each_bullet_is_its_own_sentence() -> None:
    """A plain-text bullet list has no periods: one hedge must not silence the whole list, and
    each bullet can yield its own proposal."""
    proposals = extract(
        "Requirements:\n• Must be a U.S. citizen\n• Must be at least 18 years old\n"
        "• Python experience preferred"
    )
    assert [(p.requirement_type, p.source_text) for p in proposals] == [
        (RequirementType.CITIZENSHIP, "Must be a U.S. citizen"),
        (RequirementType.MINIMUM_AGE, "Must be at least 18 years old"),
    ]


def test_long_sentence_excerpt_keeps_the_matched_phrase() -> None:
    padding = "Our synthetic team builds robots and collaborates across many disciplines; " * 8
    (proposal,) = extract(padding + "applicants must be at least 18 years old to join")
    assert len(proposal.source_text) <= MAX_EXCERPT_CHARS
    assert "at least 18 years old" in proposal.source_text
    assert proposal.source_text.startswith("…")
