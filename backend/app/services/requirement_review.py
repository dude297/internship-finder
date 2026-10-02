"""Requirement candidate review (ADR-012 §7): one atomic batch of accept/edit/reject decisions
plus an optional explicit completeness assertion.

Everything is validated before anything is mutated: an empty batch, a duplicate ID, an unknown
ID, or an invalid edited value raises and leaves the opportunity, its candidates, its
requirements, and its evaluations untouched. Functions flush only; the caller commits.
"""

import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session, selectinload

from app.enums import ExtractionMethod, FactReviewState, RequirementsAssessmentStatus
from app.models import Opportunity, OpportunityRequirement, OpportunityRequirementCandidate
from app.repositories import evaluate_if_changed, get_profile
from app.schemas.opportunity import RequirementBody, RequirementResponse
from app.schemas.requirement_review import (
    CandidateAccept,
    RequirementCandidateResponse,
    RequirementReviewRequest,
    RequirementReviewResponse,
    RequirementReviewResult,
)


class InvalidReview(ValueError):
    """The review batch failed validation. Nothing was changed."""


class UnknownCandidate(ValueError):
    """An ID in the batch isn't a candidate of this opportunity."""


_STATE_RANK = {
    FactReviewState.PENDING: 0,
    FactReviewState.ACCEPTED: 1,
    FactReviewState.REJECTED: 2,
}


def get_opportunity_for_review(db: Session, opportunity_id: uuid.UUID) -> Opportunity | None:
    """Opportunity with its candidates and canonical requirements loaded, for the review
    endpoints. `None` when the opportunity doesn't exist."""
    return db.get(
        Opportunity,
        opportunity_id,
        options=[
            selectinload(Opportunity.requirement_candidates),
            selectinload(Opportunity.requirements),
        ],
    )


def review_response(db: Session, opportunity: Opportunity) -> RequirementReviewResponse:
    candidates = sorted(
        opportunity.requirement_candidates,
        key=lambda c: (_STATE_RANK[c.review_state], c.created_at, c.id),
    )
    return RequirementReviewResponse(
        opportunity_id=opportunity.id,
        requirements_assessment_status=opportunity.requirements_assessment_status,
        requirements_stale_since=opportunity.requirements_stale_since,
        manually_curated=opportunity.manually_curated_at is not None,
        candidates=[RequirementCandidateResponse.model_validate(c) for c in candidates],
        requirements=[RequirementResponse.model_validate(r) for r in opportunity.requirements],
    )


def _merged_body(
    candidate: OpportunityRequirementCandidate, edit: CandidateAccept
) -> RequirementBody:
    """The candidate's proposal with the edit's non-null fields overlaid, validated through the
    same rules a manually-typed requirement obeys. Omitted edit fields keep the candidate's."""
    return RequirementBody(
        requirement_type=candidate.requirement_type,
        value=edit.value if edit.value is not None else candidate.value,
        applies_at=edit.applies_at if edit.applies_at is not None else candidate.applies_at,
        reference_date=(
            edit.reference_date if edit.reference_date is not None else candidate.reference_date
        ),
    )


def _find_requirement(
    opportunity: Opportunity, requirement_id: uuid.UUID | None
) -> OpportunityRequirement | None:
    if requirement_id is None:
        return None
    for requirement in opportunity.requirements:
        if requirement.id == requirement_id:
            return requirement
    return None


def _new_requirement(
    candidate: OpportunityRequirementCandidate, merged: RequirementBody
) -> OpportunityRequirement:
    return OpportunityRequirement(
        # Explicit, not the column's default=uuid.uuid4: that default is only applied at flush,
        # but the candidate link needs the ID before this batch flushes.
        id=uuid.uuid4(),
        requirement_type=candidate.requirement_type,
        value=merged.value,
        applies_at=merged.applies_at,
        reference_date=merged.reference_date,
        source_text=candidate.source_text,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name=candidate.extractor_name,
        extractor_version=candidate.extractor_version,
    )


def apply_review(
    db: Session, opportunity: Opportunity, body: RequirementReviewRequest
) -> RequirementReviewResult:
    if not body.accept and not body.reject and body.assessment_status is None:
        raise InvalidReview("The review batch is empty.")

    all_ids = [item.id for item in body.accept] + list(body.reject)
    if len(set(all_ids)) != len(all_ids):
        raise InvalidReview("A candidate ID appears more than once in the batch.")

    by_id = {c.id: c for c in opportunity.requirement_candidates}

    def _candidate(candidate_id: uuid.UUID) -> OpportunityRequirementCandidate:
        candidate = by_id.get(candidate_id)
        if candidate is None:
            raise UnknownCandidate(str(candidate_id))
        return candidate

    # --- validate everything first; nothing below this point mutates on failure ---
    accepts: list[tuple[CandidateAccept, OpportunityRequirementCandidate, RequirementBody, bool]]
    accepts = []
    for item in body.accept:
        candidate = _candidate(item.id)
        edits = (item.value, item.applies_at, item.reference_date)
        edited = any(field is not None for field in edits)
        try:
            merged = _merged_body(candidate, item)
        except ValidationError as exc:
            raise InvalidReview(str(exc)) from exc
        accepts.append((item, candidate, merged, edited))
    rejects = [_candidate(candidate_id) for candidate_id in body.reject]

    # --- mutate ---
    for _item, candidate, merged, edited in accepts:
        if candidate.review_state in (FactReviewState.PENDING, FactReviewState.REJECTED):
            requirement = _new_requirement(candidate, merged)
            opportunity.requirements.append(requirement)
            candidate.review_state = FactReviewState.ACCEPTED
            candidate.accepted_requirement_id = requirement.id
        elif edited:
            linked = _find_requirement(opportunity, candidate.accepted_requirement_id)
            if linked is not None:
                linked.value = merged.value
                linked.applies_at = merged.applies_at
                linked.reference_date = merged.reference_date
            else:
                requirement = _new_requirement(candidate, merged)
                opportunity.requirements.append(requirement)
                candidate.accepted_requirement_id = requirement.id
        # already accepted, no edit: no-op

    for candidate in rejects:
        linked_id = candidate.accepted_requirement_id
        candidate.accepted_requirement_id = None
        candidate.review_state = FactReviewState.REJECTED
        linked = _find_requirement(opportunity, linked_id)
        if linked is not None:
            opportunity.requirements.remove(linked)

    if body.assessment_status is not None:
        opportunity.requirements_assessment_status = body.assessment_status
    elif (
        body.accept
        and opportunity.requirements_assessment_status is RequirementsAssessmentStatus.UNASSESSED
    ):
        opportunity.requirements_assessment_status = RequirementsAssessmentStatus.PARTIAL

    opportunity.requirements_stale_since = None
    db.flush()

    evaluated = False
    profile = get_profile(db)
    if profile is not None:
        evaluated = evaluate_if_changed(db, profile, opportunity) is not None

    return RequirementReviewResult(review=review_response(db, opportunity), evaluated=evaluated)
