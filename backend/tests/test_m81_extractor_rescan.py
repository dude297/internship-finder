"""ADR-015 §4: re-extracting a v1 catalog with `requirements-rules` v2 respects every owner
decision. Candidates are first produced by the frozen v1 reference through the real lifecycle,
then reviewed, then the catalog scan runs with v2."""

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import tests._extractor_v1_reference as v1
from app.enums import (
    ExtractionMethod,
    FactReviewState,
    OpportunityType,
    RequirementAppliesAt,
    RequirementsAssessmentStatus,
    RequirementType,
)
from app.models import (
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirement,
    OpportunityRequirementCandidate,
)
from app.opportunities.requirements.extractor import EXTRACTOR_VERSION
from app.services import requirement_candidates

pytestmark = pytest.mark.postgres

DESCRIPTION = "\n".join(
    [
        "Must be a U.S. citizen.",  # same meaning in v1 and v2: the owner rejects it
        "Must be at least 18 years old.",  # same meaning: the owner accepts it
        "Applicants must be U.S. citizens or permanent residents.",  # v1 mislabels it
    ]
)


def _candidates(db: Session, opportunity: Opportunity) -> dict[tuple[str, str], Any]:
    rows = db.scalars(
        select(OpportunityRequirementCandidate).where(
            OpportunityRequirementCandidate.opportunity_id == opportunity.id
        )
    ).all()
    return {(c.requirement_type.value, str(sorted(c.value.items()))): c for c in rows}


def test_v1_to_v2_rescan_preserves_reviews(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    assert EXTRACTOR_VERSION == "2"
    opportunity = Opportunity(
        title="Rescan Intern",
        organization="Example Robotics",
        opportunity_type=OpportunityType.INTERNSHIP,
        description=DESCRIPTION,
        requirements_assessment_status=RequirementsAssessmentStatus.PARTIAL,
    )
    db.add(opportunity)
    db.flush()

    # 1. v1 extraction through the real lifecycle.
    with monkeypatch.context() as patch:
        patch.setattr(requirement_candidates, "extract_requirements", v1.extract_requirements)
        patch.setattr(requirement_candidates, "EXTRACTOR_VERSION", v1.EXTRACTOR_VERSION)
        assert requirement_candidates.refresh_candidates(db, opportunity).ok
    v1_rows = _candidates(db, opportunity)
    citizenship = v1_rows[("citizenship", "[('countries', ['US'])]")]
    age = v1_rows[("minimum_age", "[('years', 18)]")]
    mislabel = v1_rows[
        ("work_authorization", "[('description', 'Authorized to work in the United States')]")
    ]
    assert {c.extractor_version for c in v1_rows.values()} == {"1"}

    # 2. Owner review: reject citizenship, accept age (linked canonical requirement).
    citizenship.review_state = FactReviewState.REJECTED
    requirement = OpportunityRequirement(
        opportunity_id=opportunity.id,
        requirement_type=RequirementType.MINIMUM_AGE,
        value={"years": 18},
        applies_at=age.applies_at,
        source_text=age.source_text,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name=age.extractor_name,
        extractor_version="1",
    )
    db.add(requirement)
    db.flush()
    age.review_state = FactReviewState.ACCEPTED
    age.accepted_requirement_id = requirement.id
    db.flush()
    evaluations_before = db.scalar(select(func.count()).select_from(OpportunityEvaluation))

    # 3. v2 catalog scan: the fingerprint changed, so this opportunity is re-extracted.
    result = requirement_candidates.scan_catalog(db)
    assert result.failed == 0
    db.refresh(opportunity)
    after = _candidates(db, opportunity)

    rejected = after[("citizenship", "[('countries', ['US'])]")]
    assert rejected.id == citizenship.id
    assert rejected.review_state == FactReviewState.REJECTED  # never resurrected
    assert rejected.is_current

    accepted = after[("minimum_age", "[('years', 18)]")]
    assert accepted.review_state == FactReviewState.ACCEPTED
    assert accepted.accepted_requirement_id == requirement.id
    canonical = db.scalars(
        select(OpportunityRequirement).where(
            OpportunityRequirement.opportunity_id == opportunity.id
        )
    ).all()
    assert [(r.id, r.value, r.extractor_version) for r in canonical] == [
        (requirement.id, {"years": 18}, "1")
    ]  # canonical requirements untouched

    # The v1 mislabel was pending: it's gone, replaced by the accurate v2 proposal (pending).
    assert mislabel.id not in {c.id for c in after.values()}
    replacement = after[("other", "[('description', 'U.S. citizen or permanent resident')]")]
    assert replacement.review_state == FactReviewState.PENDING
    assert replacement.extractor_version == "2"
    assert not any(c.requirement_type is RequirementType.WORK_AUTHORIZATION for c in after.values())
    assert replacement.applies_at in set(RequirementAppliesAt)

    # Nothing else moved: assessment status, eligibility (no evaluation was appended).
    assert opportunity.requirements_assessment_status is RequirementsAssessmentStatus.PARTIAL
    assert opportunity.requirements_stale_since is None
    assert db.scalar(select(func.count()).select_from(OpportunityEvaluation)) == evaluations_before

    # Idempotent: a second scan changes nothing.
    again = requirement_candidates.scan_catalog(db)
    assert again.refreshed == 0 and again.candidates_created == 0
