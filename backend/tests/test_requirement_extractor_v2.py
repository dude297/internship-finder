"""`requirements-rules` v2 against the synthetic corpus (`requirement_corpus_v2.py`).

Pure; no database. Runs every corpus case, pins the per-family counts, checks that every emitted
free-text label is from the fixed label table, that re-worded same-meaning text keeps its semantic
key, and records the v1-vs-v2 comparison on the same corpus (`_extractor_v1_reference.py` is a
frozen test-only copy of v1)."""

from collections import Counter
from collections.abc import Callable

import pytest

from app.opportunities.requirements import extractor as v2
from app.opportunities.requirements.identity import ExtractionInput, semantic_key
from tests import _extractor_v1_reference as v1
from tests.requirement_corpus_v2 import CASES, KNOWN_MISSES, Case, Expected

Extractor = Callable[[ExtractionInput], tuple[v2.Proposal, ...]]


def _inputs(case: Case) -> ExtractionInput:
    return ExtractionInput(
        title=case.title, description=None if case.description_none else case.text
    )


def _expected_keys(expected: tuple[Expected, ...]) -> set[str]:
    from datetime import date

    from app.enums import RequirementAppliesAt, RequirementType

    return {
        semantic_key(
            RequirementType(kind),
            value,  # type: ignore[arg-type]
            RequirementAppliesAt(applies_at),
            date.fromisoformat(ref) if ref else None,
        )
        for kind, value, applies_at, ref in expected
    }


def _keys(proposals: tuple[v2.Proposal, ...]) -> set[str]:
    return {
        semantic_key(p.requirement_type, p.value, p.applies_at, p.reference_date) for p in proposals
    }


def _id(case: Case) -> str:
    return f"{case.family}:{(case.text or case.title)[:60]}"


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_corpus_case(case: Case) -> None:
    proposals = v2.extract_requirements(_inputs(case))
    assert _keys(proposals) == _expected_keys(case.expected), [
        (p.requirement_type.value, p.value, p.applies_at.value, str(p.reference_date))
        for p in proposals
    ]
    assert len(proposals) == len(case.expected)  # no duplicate proposals for one meaning


@pytest.mark.parametrize("case", KNOWN_MISSES, ids=_id)
def test_known_miss_is_a_miss_never_a_wrong_proposal(case: Case) -> None:
    got = _keys(v2.extract_requirements(_inputs(case)))
    want = _expected_keys(case.expected)
    assert got < want, "either a wrong proposal (bug) or no longer a miss (move it to CASES)"


EXPECTED_FAMILY_COUNTS = {
    "enrollment": 51,
    "graduation": 31,
    "standing": 25,
    "citizenship": 29,
    "residency": 21,
    "work_auth": 24,
    "clearance": 14,
    "age": 31,
    "multi": 16,
    "neutral": 6,
    "title": 10,
}


def test_corpus_size_and_per_family_counts() -> None:
    everything = (*CASES, *KNOWN_MISSES)
    counts = Counter(case.family for case in everything)
    print(
        "corpus total:", len(everything), "cases:", len(CASES), "known misses:", len(KNOWN_MISSES)
    )
    print("per family:", dict(sorted(counts.items())))
    assert 200 <= len(everything) <= 260
    assert dict(counts) == EXPECTED_FAMILY_COUNTS
    assert sum(1 for case in CASES if not case.expected) >= 80  # negatives dominate


# --- the fixed label table ------------------------------------------------------------------------

LABEL_PATTERNS = (
    r"Authorized to work in the United States",
    r"Authorized to work in the United States without sponsorship",
    r"Security clearance required",
    r"U\.S\. citizen or permanent resident",
    r"U\.S\. person \(export control\)",
    r"Must be returning to school after the internship",
    r"Expected graduation: (?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) )?20\d\d "
    "– (?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) )?20\\d\\d",
    r"Expected graduation: (?:(?:on or )?(?:after|before) )?(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|"
    r"Aug|Sep|Oct|Nov|Dec) )?20\d\d",
    r"Expected graduation: 20\d\d or 20\d\d(?: or 20\d\d)*",
    r"Class standing: (?:rising )?(?:first-year|sophomore|junior|senior)"
    r"(?:(?:, | or )(?:first-year|sophomore|junior|senior))*(?: or above)?",
    r"Completed at least \d+ (?:semesters?|quarters?|terms?|years?)",
)


def test_every_free_text_description_is_a_fixed_label() -> None:
    import re

    for case in (*CASES, *KNOWN_MISSES):
        for proposal in v2.extract_requirements(_inputs(case)):
            description = proposal.value.get("description")
            if description is None:
                continue
            assert any(re.fullmatch(pattern, description) for pattern in LABEL_PATTERNS), (
                description
            )


# --- same meaning, different words => same semantic key ----------------------------------------

SAME_MEANING_GROUPS = (
    (
        "Must be a U.S. citizen or permanent resident.",
        "Open to US citizens and green card holders.",
        "Applicants must be U.S. citizens or lawful permanent residents.",
    ),
    (
        "Graduating between December 2027 and June 2029.",
        "Expected graduation date between December 2027 and June 2029.",
        "Students graduating between Dec 2027 and Jun 2029 are eligible.",
    ),
    (
        "Class of 2028 or 2029",
        "Graduating in 2028 or 2029.",
        "Expected graduation between 2028 and 2029.",
    ),
    (
        "Must be authorized to work in the US without sponsorship.",
        "We will not sponsor visas now or in the future.",
        "Sponsorship is not available for this role.",
        "Candidates must not require visa sponsorship.",
    ),
    (
        "An active security clearance is required.",
        "Must hold an active Top Secret clearance.",
        "Active Secret clearance required.",
    ),
    (
        "Must be a U.S. citizen.",
        "Applicants must be US citizens.",
        "U.S. citizenship is required.",
        "Applicants must be citizens of the United States.",
    ),
    (
        "Must be currently pursuing a bachelor's degree.",
        "Must be a current undergraduate student.",
        "Currently enrolled in an accredited four-year college or university.",
    ),
    (
        "Must be at least 18 years old.",
        "Must be 18 or older.",
        "Minimum age: 18.",
    ),
)


@pytest.mark.parametrize("group", SAME_MEANING_GROUPS, ids=lambda g: g[0][:40])
def test_rewording_keeps_the_semantic_key(group: tuple[str, ...]) -> None:
    key_sets = [
        _keys(v2.extract_requirements(ExtractionInput(title="Intern", description=text)))
        for text in group
    ]
    assert len(key_sets[0]) == 1
    assert all(keys == key_sets[0] for keys in key_sets), group


def test_v1_labels_keep_their_keys() -> None:
    """v1 reviewed decisions keep matching: the two v1 labels are unchanged."""
    assert v2.WORK_AUTH_LABEL == v1.WORK_AUTH_LABEL
    assert v2.OTHER_SECURITY_CLEARANCE_LABEL == v1.OTHER_SECURITY_CLEARANCE_LABEL


def test_categories_are_never_collapsed() -> None:
    def kinds(text: str) -> list[tuple[str, str | None]]:
        return [
            (p.requirement_type.value, p.value.get("description"))
            for p in v2.extract_requirements(ExtractionInput(title="Intern", description=text))
        ]

    assert kinds("Must be a U.S. citizen.") == [("citizenship", None)]
    assert kinds("Must be a U.S. citizen or permanent resident.") == [
        ("other", v2.OTHER_CITIZEN_OR_PR_LABEL)
    ]
    assert kinds("Must be a U.S. person.") == [("other", v2.OTHER_US_PERSON_LABEL)]
    assert kinds("Must be authorized to work in the U.S.") == [
        ("work_authorization", v2.WORK_AUTH_LABEL)
    ]


# --- v1 vs v2 on the corpus ---------------------------------------------------------------------


def _score(extractor: Extractor) -> dict[str, float]:
    correct = emitted = true_positive = wrong_cases = expected_total = 0
    everything = (*CASES, *KNOWN_MISSES)
    for case in everything:
        proposals = extractor(_inputs(case))
        got = _keys(proposals)
        want = _expected_keys(case.expected)
        correct += got == want
        emitted += len(got)
        true_positive += len(got & want)
        expected_total += len(want)
        wrong_cases += bool(got - want)
    return {
        "cases": len(everything),
        "exactly_correct": correct,
        "proposals": emitted,
        "true_positive": true_positive,
        "false_proposals": emitted - true_positive,
        "cases_with_a_wrong_proposal": wrong_cases,
        "expected_requirements": expected_total,
        "precision": true_positive / emitted if emitted else 1.0,
        "recall": true_positive / expected_total,
    }


def test_v1_vs_v2_corpus_comparison() -> None:
    old = _score(v1.extract_requirements)  # type: ignore[arg-type]
    new = _score(v2.extract_requirements)
    print("\nmetric                        v1      v2")
    for metric in old:
        print(f"{metric:<28} {old[metric]:>7.3f} {new[metric]:>7.3f}")
    assert new["exactly_correct"] > old["exactly_correct"]
    assert new["recall"] > old["recall"]
    # precision first: v2 must not regress precision, and wrong proposals must be rare.
    assert new["precision"] >= old["precision"]
    assert new["precision"] >= 0.97
    assert new["cases_with_a_wrong_proposal"] <= old["cases_with_a_wrong_proposal"]
