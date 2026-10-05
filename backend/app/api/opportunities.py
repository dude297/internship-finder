import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.enums import (
    FactReviewState,
    OpportunityType,
    RemoteMode,
    RequirementsAssessmentStatus,
)
from app.models import Opportunity, OpportunityRequirementCandidate
from app.repositories import get_profile
from app.schemas.application import ApplicationBody, ApplicationResponse
from app.schemas.opportunity import (
    EvaluationResponse,
    OpportunityBody,
    OpportunityDetail,
    OpportunityPage,
)
from app.services import discovery
from app.services import opportunities as service

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _load(db: DbSession, opportunity_id: uuid.UUID) -> Opportunity:
    opportunity = service.get_opportunity(db, opportunity_id)
    if opportunity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opportunity not found.")
    return opportunity


def _pending_requirement_count(db: DbSession, opportunity_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count()).where(
                OpportunityRequirementCandidate.opportunity_id == opportunity_id,
                OpportunityRequirementCandidate.review_state == FactReviewState.PENDING,
            )
        )
        or 0
    )


def _detail(db: DbSession, opportunity: Opportunity) -> OpportunityDetail:
    detail = OpportunityDetail.model_validate(opportunity)
    detail.origin, detail.availability = discovery.provenance(opportunity.source_records)
    detail.sources = discovery.records_response(opportunity.source_records)
    evaluation = service.current_evaluation(db, opportunity)
    detail.latest_evaluation = EvaluationResponse.model_validate(evaluation) if evaluation else None
    detail.profile_exists = get_profile(db) is not None
    detail.pending_requirement_count = _pending_requirement_count(db, opportunity.id)
    detail.needs_date_verification = discovery.needs_date_verification(opportunity.verify_by)
    return detail


MAX_PAGE_SIZE = 100
TODAY_MIN, TODAY_MAX = date(2000, 1, 1), date(2999, 12, 31)


@router.get("")
def list_opportunities(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    q: Annotated[str | None, Query(max_length=200)] = None,
    availability: discovery.AvailabilityFilter = "open",
    source: Annotated[uuid.UUID | Literal["manual"] | None, Query()] = None,
    eligibility: discovery.EligibilityFilter | None = None,
    application_status: discovery.ApplicationFilter | None = None,
    remote_mode: RemoteMode | None = None,
    opportunity_type: OpportunityType | None = None,
    requirements_assessment_status: RequirementsAssessmentStatus | None = None,
    requirement_review: discovery.RequirementReviewFilter | None = None,
    deadline_within: discovery.DeadlineWithin | None = None,
    has_deadline: bool | None = None,
    needs_date_verification: bool | None = None,
    today: date | None = None,
    sort: discovery.Sort = "newest",
) -> OpportunityPage:
    """One page of opportunities with server-side search and filters. `sort=recommended` orders
    by eligibility status, then fit score; `newest` (default) by posted date; `deadline` by
    application deadline (upcoming soonest first, then unknown, then passed). `today` (ADR-012
    §14, the client's local date) drives the deadline filters and sort,
    defaulting to the server's UTC date."""
    # Bounded so date arithmetic (today + 30 days) can't overflow; any plausible date passes, so
    # tests can pin "today" (ADR-012 §14).
    if today is not None and not TODAY_MIN <= today <= TODAY_MAX:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "today must be between 2000 and 2999."
        )
    filters = discovery.Filters(
        q=q or None,
        availability=availability,
        source=source,
        eligibility=eligibility,
        application_status=application_status,
        remote_mode=remote_mode,
        opportunity_type=opportunity_type,
        requirements_assessment_status=requirements_assessment_status,
        requirement_review=requirement_review,
        deadline_within=deadline_within,
        has_deadline=has_deadline,
        needs_date_verification=needs_date_verification,
        today=today,
    )
    items, total = discovery.list_page(db, filters, limit, offset, sort)
    return OpportunityPage(items=items, total=total, limit=limit, offset=offset)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_opportunity(body: OpportunityBody, db: DbSession) -> OpportunityDetail:
    opportunity = service.create_opportunity(db, body)
    db.commit()
    return _detail(db, opportunity)


@router.get("/{opportunity_id}")
def read_opportunity(opportunity_id: uuid.UUID, db: DbSession) -> OpportunityDetail:
    return _detail(db, _load(db, opportunity_id))


@router.put("/{opportunity_id}")
def replace_opportunity(
    opportunity_id: uuid.UUID, body: OpportunityBody, db: DbSession
) -> OpportunityDetail:
    opportunity = _load(db, opportunity_id)
    service.update_opportunity(db, opportunity, body)
    db.commit()
    return _detail(db, opportunity)


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity(opportunity_id: uuid.UUID, db: DbSession) -> None:
    db.delete(_load(db, opportunity_id))
    db.commit()


@router.post("/{opportunity_id}/evaluate", status_code=status.HTTP_201_CREATED)
def evaluate_opportunity(opportunity_id: uuid.UUID, db: DbSession) -> EvaluationResponse:
    """Append a fresh evaluation (current profile, opportunity, requirements, rules v1)."""
    evaluation = service.evaluate(db, _load(db, opportunity_id))
    if evaluation is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Create your profile before evaluating eligibility."
        )
    db.commit()
    return EvaluationResponse.model_validate(evaluation)


@router.put("/{opportunity_id}/application")
def put_application(
    opportunity_id: uuid.UUID, body: ApplicationBody, db: DbSession
) -> ApplicationResponse:
    """Start or update application tracking. Doesn't affect eligibility."""
    application = service.save_application(db, _load(db, opportunity_id), body)
    db.commit()
    return ApplicationResponse.model_validate(application)


@router.delete("/{opportunity_id}/application", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(opportunity_id: uuid.UUID, db: DbSession) -> None:
    opportunity = _load(db, opportunity_id)
    if opportunity.application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This opportunity isn't being tracked.")
    opportunity.application = None
    db.commit()
