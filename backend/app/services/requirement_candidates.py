"""Requirement candidate lifecycle: refresh, staleness, and the catalog scan (ADR-012 §6, §9).

Functions flush only; callers commit. Never read by the eligibility engine (it only reads
`opportunity_requirements`); this module is the only writer of `opportunity_requirement_candidates`
besides the review API (Agent 3), which only edits review state.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.enums import FactReviewState, RequirementsAssessmentStatus
from app.models import Opportunity, OpportunityRequirementCandidate
from app.opportunities.requirements.extractor import (
    EXTRACTOR_NAME,
    EXTRACTOR_VERSION,
    extract_requirements,
)
from app.opportunities.requirements.identity import (
    ExtractionInput,
    extraction_fingerprint,
    semantic_key,
)

logger = logging.getLogger(__name__)

CATALOG_SCAN_BATCH_SIZE = 200


@dataclass(frozen=True)
class RefreshOutcome:
    ok: bool
    candidates_created: int = 0


def refresh_candidates(db: Session, opportunity: Opportunity) -> RefreshOutcome:
    """Re-extract and reconcile candidates (ADR-012 §6 "Refresh"). Never raises for an extractor
    failure: logs opportunity id and exception type only (never the posting text), leaves the
    stored fingerprint and every candidate untouched, and returns `ok=False` so the catalog scan
    retries it later.

    Expects `opportunity.requirements` and `opportunity.requirement_candidates` to be usable
    (eagerly loaded by the caller for batches, or lazily loaded within an open session)."""
    inputs = ExtractionInput.model_validate(opportunity)
    try:
        proposals = extract_requirements(inputs)
    except Exception as error:  # noqa: BLE001 - a failing extractor must never fail the caller
        logger.error(
            "requirement extraction failed opportunity_id=%s exception_type=%s",
            opportunity.id,
            type(error).__name__,
        )
        return RefreshOutcome(ok=False)

    canonical_keys = {
        semantic_key(r.requirement_type, r.value, r.applies_at, r.reference_date)
        for r in opportunity.requirements
    }
    existing_by_key = {c.semantic_key: c for c in opportunity.requirement_candidates}
    proposed_keys: set[str] = set()
    created = 0

    for proposal in proposals:
        key = semantic_key(
            proposal.requirement_type, proposal.value, proposal.applies_at, proposal.reference_date
        )
        if key in canonical_keys:
            continue  # already represented by a canonical requirement (ADR-012 §3)
        proposed_keys.add(key)
        existing = existing_by_key.get(key)
        if existing is None:
            db.add(
                OpportunityRequirementCandidate(
                    opportunity_id=opportunity.id,
                    semantic_key=key,
                    requirement_type=proposal.requirement_type,
                    value=proposal.value,
                    applies_at=proposal.applies_at,
                    reference_date=proposal.reference_date,
                    source_text=proposal.source_text,
                    extractor_name=EXTRACTOR_NAME,
                    extractor_version=EXTRACTOR_VERSION,
                    review_state=FactReviewState.PENDING,
                    is_current=True,
                )
            )
            created += 1
        else:
            # Same key: same normalized value, type, applies_at, and reference date. Only the
            # evidence and extractor version can have changed.
            existing.is_current = True
            existing.source_text = proposal.source_text
            existing.extractor_name = EXTRACTOR_NAME
            existing.extractor_version = EXTRACTOR_VERSION

    for key, candidate in existing_by_key.items():
        if key in proposed_keys:
            continue
        if candidate.review_state == FactReviewState.PENDING:
            db.delete(candidate)
        else:
            candidate.is_current = False  # reviewed decisions are kept, just marked stale

    opportunity.requirement_extraction_fingerprint = extraction_fingerprint(
        inputs, EXTRACTOR_NAME, EXTRACTOR_VERSION
    )
    db.flush()
    return RefreshOutcome(ok=True, candidates_created=created)


def invalidate_after_source_change(db: Session, opportunity: Opportunity, now: datetime) -> None:
    """Steps 1-2 of ADR-012 §6 "Source change after review": only when the owner had already
    reviewed this opportunity's requirements (an explicit assessment, or any reviewed candidate).
    Candidate refresh (step 3) and re-evaluation (step 5) are the caller's job, in that order, so
    staleness and status are already updated before the pipeline's `evaluate_if_changed` runs
    (step 5 reads the assessment status)."""
    unassessed = RequirementsAssessmentStatus.UNASSESSED
    reviewed = opportunity.requirements_assessment_status != unassessed or any(
        c.review_state != FactReviewState.PENDING for c in opportunity.requirement_candidates
    )
    if not reviewed:
        return
    if opportunity.requirements_stale_since is None:
        opportunity.requirements_stale_since = now
    if opportunity.requirements_assessment_status == RequirementsAssessmentStatus.COMPLETE:
        opportunity.requirements_assessment_status = (
            RequirementsAssessmentStatus.PARTIAL
            if opportunity.requirements
            else RequirementsAssessmentStatus.UNASSESSED
        )
    db.flush()


@dataclass(frozen=True)
class ScanResult:
    scanned: int
    refreshed: int
    unchanged: int
    failed: int
    candidates_created: int


def scan_catalog(db: Session, batch_size: int = CATALOG_SCAN_BATCH_SIZE) -> ScanResult:
    """ADR-012 §9: keyset batches over every opportunity, refreshing only rows whose stored
    extraction fingerprint isn't current. Idempotent; never accepts, changes an assessment
    status, marks staleness, or evaluates. Commits once per batch."""
    scanned = refreshed = unchanged = failed = candidates_created = 0
    after: uuid.UUID | None = None
    while True:
        query = (
            select(Opportunity)
            .options(
                selectinload(Opportunity.requirements),
                selectinload(Opportunity.requirement_candidates),
            )
            .order_by(Opportunity.id)
            .limit(batch_size)
        )
        if after is not None:
            query = query.where(Opportunity.id > after)
        batch = db.scalars(query).all()
        if not batch:
            break
        for opportunity in batch:
            scanned += 1
            inputs = ExtractionInput.model_validate(opportunity)
            current_fingerprint = extraction_fingerprint(inputs, EXTRACTOR_NAME, EXTRACTOR_VERSION)
            if opportunity.requirement_extraction_fingerprint == current_fingerprint:
                unchanged += 1
                continue
            outcome = refresh_candidates(db, opportunity)
            if outcome.ok:
                refreshed += 1
                candidates_created += outcome.candidates_created
            else:
                failed += 1
        db.commit()
        after = batch[-1].id
    return ScanResult(scanned, refreshed, unchanged, failed, candidates_created)
