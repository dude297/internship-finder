"""Requirement candidate review API (ADR-012 §7). Private, CSRF-protected like every mutation
(require_owner is mounted once on the parent router, app.main)."""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.models import Opportunity
from app.schemas.requirement_review import (
    RequirementReviewRequest,
    RequirementReviewResponse,
    RequirementReviewResult,
)
from app.services.requirement_candidates import refresh_candidates
from app.services.requirement_review import (
    InvalidReview,
    UnknownCandidate,
    apply_review,
    get_opportunity_for_review,
    review_response,
)

router = APIRouter(prefix="/opportunities", tags=["requirement-review"])


def _load(db: DbSession, opportunity_id: uuid.UUID) -> Opportunity:
    opportunity = get_opportunity_for_review(db, opportunity_id)
    if opportunity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opportunity not found.")
    return opportunity


@router.get("/{opportunity_id}/requirement-review")
def get_requirement_review(opportunity_id: uuid.UUID, db: DbSession) -> RequirementReviewResponse:
    opportunity = _load(db, opportunity_id)
    return review_response(db, opportunity)


@router.post("/{opportunity_id}/requirement-review/refresh")
def refresh_requirement_review(
    opportunity_id: uuid.UUID, db: DbSession
) -> RequirementReviewResponse:
    """Re-extract candidates now (ADR-012 §6). Never evaluates: candidates don't affect
    eligibility."""
    opportunity = _load(db, opportunity_id)
    refresh_candidates(db, opportunity)
    db.commit()
    return review_response(db, opportunity)


@router.post("/{opportunity_id}/requirement-review")
def post_requirement_review(
    opportunity_id: uuid.UUID, body: RequirementReviewRequest, db: DbSession
) -> RequirementReviewResult:
    opportunity = _load(db, opportunity_id)
    try:
        result = apply_review(db, opportunity, body)
    except UnknownCandidate as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown candidate: {exc}") from exc
    except InvalidReview as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.commit()
    return result
