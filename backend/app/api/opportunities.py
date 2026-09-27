import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.models import Opportunity
from app.repositories import get_profile
from app.schemas.application import ApplicationBody, ApplicationResponse
from app.schemas.opportunity import (
    EvaluationResponse,
    OpportunityBody,
    OpportunityDetail,
    OpportunitySummary,
)
from app.services import opportunities as service

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _load(db: DbSession, opportunity_id: uuid.UUID) -> Opportunity:
    opportunity = service.get_opportunity(db, opportunity_id)
    if opportunity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opportunity not found.")
    return opportunity


def _detail(db: DbSession, opportunity: Opportunity) -> OpportunityDetail:
    detail = OpportunityDetail.model_validate(opportunity)
    evaluation = service.current_evaluation(db, opportunity)
    detail.latest_evaluation = EvaluationResponse.model_validate(evaluation) if evaluation else None
    detail.profile_exists = get_profile(db) is not None
    return detail


@router.get("")
def list_opportunities(db: DbSession) -> list[OpportunitySummary]:
    return [
        OpportunitySummary(
            id=o.id,
            title=o.title,
            organization=o.organization,
            opportunity_type=o.opportunity_type,
            location=o.location,
            remote_mode=o.remote_mode,
            application_deadline=o.application_deadline,
            start_date=o.start_date,
            requirements_assessment_status=o.requirements_assessment_status,
            eligibility_status=e.eligibility_status if e else None,
            evaluated_at=e.evaluated_at if e else None,
            application_status=o.application.status if o.application else None,
        )
        for o, e in service.list_opportunities(db)
    ]


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
