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
from app.opportunities.requirements.extractor import EXTRACTOR_NAME
from app.opportunities.requirements.identity import requirement_key
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


def get_opportunity_for_review(
    db: Session, opportunity_id: uuid.UUID, *, lock: bool = False
) -> Opportunity | None:
    """Opportunity with its candidates and canonical requirements loaded, for the review
    endpoints. `None` when the opportunity doesn't exist. `lock` takes a row lock on the
    opportunity for the rest of the transaction, so two concurrent review batches (or a batch
    and a refresh) of one opportunity run one after the other instead of both accepting the
    same suggestion."""
    return db.get(
        Opportunity,
        opportunity_id,
        options=[
            selectinload(Opportunity.requirement_candidates),
            selectinload(Opportunity.requirements),
        ],
        with_for_update=lock,
        populate_existing=lock,
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
    """The candidate's proposal with the edit overlaid, validated through the same rules a
    manually-typed requirement obeys. Omitted edit fields keep the candidate's; when the edit
    names applies_at or reference_date, the date is taken from the edit (so it can be cleared)."""
    dated = bool({"applies_at", "reference_date"} & edit.model_fields_set)
    return RequirementBody(
        requirement_type=candidate.requirement_type,
        value=edit.value if edit.value is not None else candidate.value,
        applies_at=edit.applies_at if edit.applies_at is not None else candidate.applies_at,
        reference_date=edit.reference_date if dated else candidate.reference_date,
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


def _candidate_managed(requirement: OpportunityRequirement) -> bool:
    """Created by accepting a suggestion, not typed by the owner. Only these rows may ever be
    deleted or replaced by a review; a manual row (including one rewritten by an owner edit)
    is never touched here (manual data wins, ADR-012 §7)."""
    return (
        requirement.extraction_method is ExtractionMethod.DETERMINISTIC_PARSER
        and requirement.extractor_name == EXTRACTOR_NAME
    )


def _link_or_create(
    opportunity: Opportunity, candidate: OpportunityRequirementCandidate, merged: RequirementBody
) -> None:
    """Link to a canonical requirement that already means exactly this (e.g. one typed by hand,
    or one another accepted suggestion created), or create one: accepting never duplicates a
    requirement and never mutates an existing one (ADR-012 §7)."""
    key = requirement_key(merged)
    existing = next((r for r in opportunity.requirements if requirement_key(r) == key), None)
    if existing is None:
        existing = _new_requirement(candidate, merged)
        opportunity.requirements.append(existing)
    candidate.accepted_requirement_id = existing.id


def _release(opportunity: Opportunity, requirement_id: uuid.UUID | None) -> bool:
    """Called after a candidate dropped its link: delete the requirement only when it is
    candidate-managed and no accepted candidate still links to it. True if it was deleted."""
    requirement = _find_requirement(opportunity, requirement_id)
    if requirement is None or not _candidate_managed(requirement):
        return False
    if any(
        c.review_state is FactReviewState.ACCEPTED and c.accepted_requirement_id == requirement.id
        for c in opportunity.requirement_candidates
    ):
        return False
    opportunity.requirements.remove(requirement)
    return True


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
        edited = bool({"value", "applies_at", "reference_date"} & item.model_fields_set)
        try:
            merged = _merged_body(candidate, item)
        except ValidationError as exc:
            raise InvalidReview(str(exc)) from exc
        accepts.append((item, candidate, merged, edited))
    rejects = [_candidate(candidate_id) for candidate_id in body.reject]

    # --- mutate ---
    for _item, candidate, merged, edited in accepts:
        if candidate.review_state in (FactReviewState.PENDING, FactReviewState.REJECTED):
            _link_or_create(opportunity, candidate, merged)
            candidate.review_state = FactReviewState.ACCEPTED
        elif edited:
            # Relink rather than rewrite: the linked row may be manual or shared with another
            # accepted suggestion. The old row goes only if this left it candidate-owned orphan.
            previous = candidate.accepted_requirement_id
            _link_or_create(opportunity, candidate, merged)
            if candidate.accepted_requirement_id != previous:
                _release(opportunity, previous)
        # already accepted, no edit: no-op

    removed_requirement = False
    for candidate in rejects:
        previous = candidate.accepted_requirement_id
        candidate.accepted_requirement_id = None
        candidate.review_state = FactReviewState.REJECTED
        removed_requirement |= _release(opportunity, previous)

    status = opportunity.requirements_assessment_status
    if body.assessment_status is not None:
        opportunity.requirements_assessment_status = body.assessment_status
    elif removed_requirement and status is RequirementsAssessmentStatus.COMPLETE:
        # "Complete" was asserted for a set that just lost a requirement. Removing one must never
        # silently make eligibility more permissive: the owner re-asserts completeness explicitly.
        opportunity.requirements_assessment_status = (
            RequirementsAssessmentStatus.PARTIAL
            if opportunity.requirements
            else RequirementsAssessmentStatus.UNASSESSED
        )
    elif body.accept and status is RequirementsAssessmentStatus.UNASSESSED:
        opportunity.requirements_assessment_status = RequirementsAssessmentStatus.PARTIAL

    opportunity.requirements_stale_since = None
    db.flush()

    evaluated = False
    profile = get_profile(db)
    if profile is not None:
        evaluated = evaluate_if_changed(db, profile, opportunity) is not None

    return RequirementReviewResult(review=review_response(db, opportunity), evaluated=evaluated)
