"""Global requirement review queue API (ADR-024). Private and CSRF-protected like every
mutation (require_owner is mounted once on the parent router, app.main). Single accept/reject
goes through the existing POST /opportunities/{id}/requirement-review (ADR-012 §7)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession
from app.enums import IngestionSourceKind, RequirementType
from app.schemas.requirement_review import (
    MAX_QUEUE_PAGE,
    BatchRejectRequest,
    BatchRejectResult,
    QueuePage,
)
from app.services import requirement_queue as service
from app.services.requirement_review import InvalidReview, UnknownCandidate

router = APIRouter(prefix="/requirement-review", tags=["requirement-review"])

DAY_MIN, DAY_MAX = date(2000, 1, 1), date(2999, 12, 31)


@router.get("/queue")
def read_queue(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=MAX_QUEUE_PAGE)] = 25,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    requirement_type: RequirementType | None = None,
    extractor_name: Annotated[str | None, Query(max_length=100)] = None,
    extractor_version: Annotated[str | None, Query(max_length=50)] = None,
    organization: Annotated[str | None, Query(max_length=200)] = None,
    source_kind: IngestionSourceKind | None = None,
    opportunity_id: uuid.UUID | None = None,
    posting_changed: bool = False,
    created_since: date | None = None,
    today: date | None = None,
) -> QueuePage:
    # Bounded like the inbox's `today`, so date arithmetic can't overflow.
    for value in (created_since, today):
        if value is not None and not DAY_MIN <= value <= DAY_MAX:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Dates must be between 2000 and 2999."
            )
    return service.build_queue(
        db,
        limit=limit,
        offset=offset,
        today=today,
        requirement_type=requirement_type,
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        organization=organization,
        source_kind=source_kind,
        opportunity_id=opportunity_id,
        posting_changed=posting_changed,
        created_since=created_since,
    )


@router.post("/reject-batch")
def reject_batch(body: BatchRejectRequest, db: DbSession) -> BatchRejectResult:
    try:
        result = service.reject_batch(db, body.candidate_ids)
    except UnknownCandidate as exc:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown candidate: {exc}") from exc
    except InvalidReview as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.commit()
    return result
