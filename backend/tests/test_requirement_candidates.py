"""Requirement candidate lifecycle, staleness, ingestion integration, and the catalog scan
(ADR-012 §6, §9) against real PostgreSQL. Synthetic payloads only."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import (
    EducationLevel,
    ExtractionMethod,
    FactReviewState,
    IngestionSourceKind,
    OpportunityType,
    RequirementAppliesAt,
    RequirementsAssessmentStatus,
    RequirementType,
)
from app.ingestion.pipeline import sync_source
from app.models import (
    IngestionRun,
    IngestionSource,
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirement,
    OpportunityRequirementCandidate,
    Profile,
)
from app.repositories import evaluate_and_save, latest_evaluation
from app.schemas.opportunity import OpportunityBody, RequirementBody
from app.schemas.requirement_review import CandidateAccept, RequirementReviewRequest
from app.services.opportunities import create_opportunity, update_opportunity
from app.services.requirement_candidates import (
    invalidate_after_source_change,
    refresh_candidates,
    scan_catalog,
)
from app.services.requirement_review import apply_review
from tests.ingestion_fixtures import GREENHOUSE_BOARD, FakeSource, greenhouse_board, greenhouse_job

pytestmark = pytest.mark.postgres


# --- fixtures -----------------------------------------------------------------------------------


@pytest.fixture
def gh_source(db: Session) -> IngestionSource:
    source = IngestionSource(
        kind=IngestionSourceKind.GREENHOUSE,
        identifier=GREENHOUSE_BOARD,
        display_name="Example Robotics",
    )
    db.add(source)
    db.commit()
    return source


@pytest.fixture
def web() -> FakeSource:
    return FakeSource()


@pytest.fixture
def profile(db: Session) -> Profile:
    row = Profile(
        current_education_level=EducationLevel.HIGH_SCHOOL,
        education_status_as_of=date(2040, 9, 1),
        expected_graduation_date=date(2041, 6, 10),
        expected_enrollment_date=date(2041, 8, 25),
        expected_future_education_level=EducationLevel.UNDERGRADUATE,
        date_of_birth=date(2023, 6, 20),
    )
    db.add(row)
    db.commit()
    return row


def make_opportunity(db: Session, description: str | None, **overrides: Any) -> Opportunity:
    opportunity = Opportunity(
        title=overrides.pop("title", "Synthetic Robotics Intern"),
        organization=overrides.pop("organization", "Example Robotics"),
        opportunity_type=overrides.pop("opportunity_type", OpportunityType.INTERNSHIP),
        description=description,
        **overrides,
    )
    db.add(opportunity)
    db.flush()
    return opportunity


def candidates(db: Session, opportunity: Opportunity) -> list[OpportunityRequirementCandidate]:
    return list(
        db.scalars(
            select(OpportunityRequirementCandidate)
            .where(OpportunityRequirementCandidate.opportunity_id == opportunity.id)
            .order_by(OpportunityRequirementCandidate.created_at)
        )
    )


AGE_18 = "You must be at least 18."
US_CITIZEN = "Must be a U.S. citizen."


# --- refresh_candidates: basic lifecycle ---------------------------------------------------------


def test_refresh_creates_pending(db: Session) -> None:
    opportunity = make_opportunity(db, AGE_18)
    outcome = refresh_candidates(db, opportunity)
    assert outcome.ok
    assert outcome.candidates_created == 1
    rows = candidates(db, opportunity)
    assert len(rows) == 1
    assert rows[0].review_state == FactReviewState.PENDING
    assert rows[0].requirement_type == RequirementType.MINIMUM_AGE
    assert rows[0].value == {"years": 18}
    assert rows[0].is_current is True
    assert opportunity.requirement_extraction_fingerprint is not None


def test_refresh_is_idempotent(db: Session) -> None:
    opportunity = make_opportunity(db, AGE_18)
    refresh_candidates(db, opportunity)
    first = candidates(db, opportunity)
    outcome = refresh_candidates(db, opportunity)
    assert outcome.candidates_created == 0
    second = candidates(db, opportunity)
    assert [r.id for r in first] == [r.id for r in second]
    assert [r.updated_at for r in first] == [r.updated_at for r in second]


def test_pending_removed_when_no_longer_proposed(db: Session) -> None:
    opportunity = make_opportunity(db, AGE_18)
    refresh_candidates(db, opportunity)
    assert len(candidates(db, opportunity)) == 1

    opportunity.description = "Nothing requirement-shaped here."
    refresh_candidates(db, opportunity)
    assert candidates(db, opportunity) == []


def test_accepted_kept_with_is_current_false_when_no_longer_proposed(db: Session) -> None:
    opportunity = make_opportunity(db, AGE_18)
    refresh_candidates(db, opportunity)
    (row,) = candidates(db, opportunity)
    row.review_state = FactReviewState.ACCEPTED
    db.flush()

    opportunity.description = "Nothing requirement-shaped here."
    refresh_candidates(db, opportunity)
    (row,) = candidates(db, opportunity)
    assert row.review_state == FactReviewState.ACCEPTED
    assert row.is_current is False


def test_rejected_not_resurrected_by_rephrased_text(db: Session) -> None:
    opportunity = make_opportunity(db, AGE_18)
    refresh_candidates(db, opportunity)
    (row,) = candidates(db, opportunity)
    row.review_state = FactReviewState.REJECTED
    db.flush()

    # Same meaning, different words: must not create a second (pending) row.
    opportunity.description = "Minimum age: 18."
    refresh_candidates(db, opportunity)
    rows = candidates(db, opportunity)
    assert len(rows) == 1
    assert rows[0].review_state == FactReviewState.REJECTED
    assert rows[0].is_current is True


def test_accepted_not_duplicated_on_rerun(db: Session) -> None:
    opportunity = make_opportunity(db, AGE_18)
    refresh_candidates(db, opportunity)
    (row,) = candidates(db, opportunity)
    row.review_state = FactReviewState.ACCEPTED
    db.flush()

    refresh_candidates(db, opportunity)
    rows = candidates(db, opportunity)
    assert len(rows) == 1
    assert rows[0].review_state == FactReviewState.ACCEPTED


def test_accepted_candidate_stays_current_after_its_canonical_requirement_exists(
    db: Session,
) -> None:
    """An unedited accept creates a canonical requirement with the same semantic key; the next
    refresh must neither duplicate it nor mark the accepted suggestion 'no longer in posting'."""
    opportunity = make_opportunity(db, AGE_18)
    refresh_candidates(db, opportunity)
    (row,) = candidates(db, opportunity)
    apply_review(db, opportunity, RequirementReviewRequest(accept=[CandidateAccept(id=row.id)]))

    refresh_candidates(db, opportunity)
    (row,) = candidates(db, opportunity)
    assert row.review_state == FactReviewState.ACCEPTED
    assert row.is_current
    assert len(opportunity.requirements) == 1


def test_canonical_equivalent_proposal_is_suppressed(db: Session) -> None:
    opportunity = make_opportunity(db, AGE_18)
    opportunity.requirements.append(
        OpportunityRequirement(
            requirement_type=RequirementType.MINIMUM_AGE,
            value={"years": 18},
            applies_at=RequirementAppliesAt.PROGRAM_START,
            extraction_method=ExtractionMethod.MANUAL,
        )
    )
    db.flush()

    outcome = refresh_candidates(db, opportunity)
    assert outcome.ok
    assert outcome.candidates_created == 0
    assert candidates(db, opportunity) == []


def test_extraction_never_changes_assessment_status(db: Session) -> None:
    opportunity = make_opportunity(db, AGE_18)
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    db.flush()
    refresh_candidates(db, opportunity)
    assert opportunity.requirements_assessment_status == RequirementsAssessmentStatus.COMPLETE


def test_pending_candidates_never_change_eligibility(db: Session, profile: Profile) -> None:
    opportunity = make_opportunity(db, AGE_18)
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    db.flush()
    without_candidates = evaluate_and_save(db, profile, opportunity)

    refresh_candidates(db, opportunity)
    assert candidates(db, opportunity) != []
    with_candidates = evaluate_and_save(db, profile, opportunity)

    assert without_candidates.eligibility_status == with_candidates.eligibility_status
    assert without_candidates.input_fingerprint == with_candidates.input_fingerprint


def test_extractor_failure_does_not_raise_and_skips_fingerprint(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    opportunity = make_opportunity(db, AGE_18)

    def _boom(_inputs: Any) -> Any:
        raise RuntimeError("synthetic failure")

    import app.services.requirement_candidates as module

    monkeypatch.setattr(module, "extract_requirements", _boom)
    outcome = refresh_candidates(db, opportunity)
    assert outcome.ok is False
    assert opportunity.requirement_extraction_fingerprint is None
    assert candidates(db, opportunity) == []


# --- invalidate_after_source_change ---------------------------------------------------------------


def test_invalidate_downgrades_complete_to_partial_when_requirements_remain(db: Session) -> None:
    opportunity = make_opportunity(db, AGE_18)
    opportunity.requirements.append(
        OpportunityRequirement(
            requirement_type=RequirementType.MINIMUM_AGE,
            value={"years": 18},
            extraction_method=ExtractionMethod.MANUAL,
        )
    )
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    db.flush()

    invalidate_after_source_change(db, opportunity, datetime.now(UTC))
    assert opportunity.requirements_stale_since is not None
    assert opportunity.requirements_assessment_status == RequirementsAssessmentStatus.PARTIAL


def test_invalidate_downgrades_complete_to_unassessed_with_no_requirements(db: Session) -> None:
    opportunity = make_opportunity(db, AGE_18)
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    db.flush()

    invalidate_after_source_change(db, opportunity, datetime.now(UTC))
    assert opportunity.requirements_assessment_status == RequirementsAssessmentStatus.UNASSESSED


def test_invalidate_is_a_noop_when_never_reviewed(db: Session) -> None:
    opportunity = make_opportunity(db, AGE_18)
    assert opportunity.requirements_assessment_status == RequirementsAssessmentStatus.UNASSESSED
    invalidate_after_source_change(db, opportunity, datetime.now(UTC))
    assert opportunity.requirements_stale_since is None


def test_invalidate_keeps_existing_stale_since(db: Session) -> None:
    first = datetime(2040, 1, 1, tzinfo=UTC)
    opportunity = make_opportunity(db, AGE_18)
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.PARTIAL
    opportunity.requirements_stale_since = first
    db.flush()
    invalidate_after_source_change(db, opportunity, datetime(2040, 2, 1, tzinfo=UTC))
    assert opportunity.requirements_stale_since == first


# --- manual create/edit ---------------------------------------------------------------------------


def test_manual_create_refreshes_candidates(db: Session) -> None:
    body = OpportunityBody(
        title="Synthetic Fellowship",
        organization="Example Institute",
        description=AGE_18,
        opportunity_type=OpportunityType.FELLOWSHIP,
        requirements=[],
    )
    opportunity = create_opportunity(db, body)
    rows = candidates(db, opportunity)
    assert len(rows) == 1
    assert rows[0].requirement_type == RequirementType.MINIMUM_AGE
    # The owner made the change: no staleness.
    assert opportunity.requirements_stale_since is None


def test_manual_edit_refreshes_candidates_without_invalidating(db: Session) -> None:
    body = OpportunityBody(
        title="Synthetic Fellowship",
        organization="Example Institute",
        description="Nothing requirement-shaped here.",
        opportunity_type=OpportunityType.FELLOWSHIP,
        requirements=[
            RequirementBody(requirement_type=RequirementType.MINIMUM_AGE, value={"years": 18})
        ],
    )
    opportunity = create_opportunity(db, body)
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    db.flush()

    edited = OpportunityBody(
        title="Synthetic Fellowship",
        organization="Example Institute",
        description=US_CITIZEN,
        opportunity_type=OpportunityType.FELLOWSHIP,
        requirements_assessment_status=RequirementsAssessmentStatus.COMPLETE,
        requirements=[
            RequirementBody(requirement_type=RequirementType.MINIMUM_AGE, value={"years": 18})
        ],
    )
    update_opportunity(db, opportunity, edited)
    rows = candidates(db, opportunity)
    assert any(r.requirement_type == RequirementType.CITIZENSHIP for r in rows)
    assert opportunity.requirements_stale_since is None
    assert opportunity.requirements_assessment_status == RequirementsAssessmentStatus.COMPLETE


# --- ingestion integration -----------------------------------------------------------------------


def sync(db: Session, source: IngestionSource, web: FakeSource) -> IngestionRun:
    return sync_source(db, source, transport=web.transport())


def test_new_ingested_item_gets_candidates(
    db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    job = greenhouse_job(content=f"<p>{AGE_18}</p>")
    web.json(
        f"https://boards-api.greenhouse.io/v1/boards/{GREENHOUSE_BOARD}/jobs?content=true",
        greenhouse_board(job),
    )
    sync(db, gh_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    rows = candidates(db, opportunity)
    assert len(rows) == 1
    assert rows[0].requirement_type == RequirementType.MINIMUM_AGE


def test_unchanged_resync_creates_zero_candidate_changes(
    db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    job = greenhouse_job(content=f"<p>{AGE_18}</p>")
    url = f"https://boards-api.greenhouse.io/v1/boards/{GREENHOUSE_BOARD}/jobs?content=true"
    web.json(url, greenhouse_board(job))
    sync(db, gh_source, web)
    db.commit()
    opportunity = db.scalars(select(Opportunity)).one()
    before = [(r.id, r.updated_at) for r in candidates(db, opportunity)]

    sync(db, gh_source, web)  # identical payload: content hash unchanged
    after = [(r.id, r.updated_at) for r in candidates(db, opportunity)]
    assert before == after


def test_material_change_on_complete_reviewed_opportunity_goes_stale(
    db: Session, gh_source: IngestionSource, web: FakeSource, profile: Profile
) -> None:
    url = f"https://boards-api.greenhouse.io/v1/boards/{GREENHOUSE_BOARD}/jobs?content=true"
    job = greenhouse_job(content=f"<p>{AGE_18}</p>")
    web.json(url, greenhouse_board(job))
    sync(db, gh_source, web)
    db.commit()
    opportunity = db.scalars(select(Opportunity)).one()

    # Owner reviews: accepts the age requirement and asserts completeness.
    opportunity.requirements.append(
        OpportunityRequirement(
            requirement_type=RequirementType.MINIMUM_AGE,
            value={"years": 18},
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        )
    )
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    db.commit()
    evaluate_and_save(db, profile, opportunity)
    db.commit()

    # Sync again with a materially different description.
    web.json(url, greenhouse_board(greenhouse_job(content=f"<p>{US_CITIZEN}</p>")))
    sync(db, gh_source, web)
    db.commit()

    opportunity = db.scalars(select(Opportunity)).one()
    assert opportunity.requirements_stale_since is not None
    assert opportunity.requirements_assessment_status == RequirementsAssessmentStatus.PARTIAL
    # The old accepted canonical requirement is kept.
    assert any(r.requirement_type == RequirementType.MINIMUM_AGE for r in opportunity.requirements)
    # A new pending candidate for the new sentence exists.
    rows = candidates(db, opportunity)
    assert any(
        r.requirement_type == RequirementType.CITIZENSHIP
        and r.review_state == FactReviewState.PENDING
        for r in rows
    )
    # A new evaluation was appended.
    evaluations = db.scalars(
        select(OpportunityEvaluation).where(OpportunityEvaluation.opportunity_id == opportunity.id)
    ).all()
    assert len(evaluations) >= 2


def test_non_material_change_does_not_go_stale(
    db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    url = f"https://boards-api.greenhouse.io/v1/boards/{GREENHOUSE_BOARD}/jobs?content=true"
    job = greenhouse_job(content=f"<p>{AGE_18}</p>")
    web.json(url, greenhouse_board(job))
    sync(db, gh_source, web)
    db.commit()
    opportunity = db.scalars(select(Opportunity)).one()
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    db.commit()

    # Same title/description/content; only the location changed (not an extraction input).
    changed_location = greenhouse_job(content=f"<p>{AGE_18}</p>", location={"name": "New City"})
    web.json(url, greenhouse_board(changed_location))
    sync(db, gh_source, web)
    db.commit()

    opportunity = db.scalars(select(Opportunity)).one()
    assert opportunity.requirements_stale_since is None
    assert opportunity.requirements_assessment_status == RequirementsAssessmentStatus.COMPLETE


def test_curated_opportunity_never_goes_stale(
    db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    url = f"https://boards-api.greenhouse.io/v1/boards/{GREENHOUSE_BOARD}/jobs?content=true"
    job = greenhouse_job(content=f"<p>{AGE_18}</p>")
    web.json(url, greenhouse_board(job))
    sync(db, gh_source, web)
    db.commit()
    opportunity = db.scalars(select(Opportunity)).one()
    opportunity.manually_curated_at = datetime.now(UTC)
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    db.commit()

    web.json(url, greenhouse_board(greenhouse_job(content=f"<p>{US_CITIZEN}</p>")))
    sync(db, gh_source, web)
    db.commit()

    opportunity = db.scalars(select(Opportunity)).one()
    assert opportunity.requirements_stale_since is None
    assert opportunity.requirements_assessment_status == RequirementsAssessmentStatus.COMPLETE


def test_extractor_exception_during_ingestion_does_not_fail_the_item(
    db: Session, gh_source: IngestionSource, web: FakeSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"https://boards-api.greenhouse.io/v1/boards/{GREENHOUSE_BOARD}/jobs?content=true"
    job = greenhouse_job(content=f"<p>{AGE_18}</p>")
    web.json(url, greenhouse_board(job))

    def _boom(_inputs: Any) -> Any:
        raise RuntimeError("synthetic failure")

    import app.services.requirement_candidates as module

    monkeypatch.setattr(module, "extract_requirements", _boom)
    run = sync(db, gh_source, web)

    from app.enums import IngestionRunStatus

    assert run.status == IngestionRunStatus.SUCCESS
    assert run.created_count == 1
    opportunity = db.scalars(select(Opportunity)).one()
    assert candidates(db, opportunity) == []
    assert opportunity.requirement_extraction_fingerprint is None


# --- scan_catalog ---------------------------------------------------------------------------------


def test_scan_catalog_is_idempotent_and_bounded(db: Session) -> None:
    opportunities = [make_opportunity(db, AGE_18, title=f"Synthetic {i}") for i in range(5)]
    db.commit()

    first = scan_catalog(db, batch_size=2)
    assert first.scanned == 5
    assert first.refreshed == 5
    assert first.candidates_created == 5

    second = scan_catalog(db, batch_size=2)
    assert second.scanned == 5
    assert second.refreshed == 0
    assert second.unchanged == 5
    assert second.candidates_created == 0

    for opportunity in opportunities:
        db.refresh(opportunity)
        assert len(candidates(db, opportunity)) == 1


def test_scan_catalog_never_changes_assessment_status_or_evaluates(
    db: Session, profile: Profile
) -> None:
    opportunity = make_opportunity(db, AGE_18)
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    db.commit()
    evaluate_and_save(db, profile, opportunity)
    db.commit()
    before = latest_evaluation(db, profile.id, opportunity.id)

    scan_catalog(db)

    db.refresh(opportunity)
    assert opportunity.requirements_assessment_status == RequirementsAssessmentStatus.COMPLETE
    after = latest_evaluation(db, profile.id, opportunity.id)
    assert before is not None and after is not None
    assert before.id == after.id


def test_extractor_version_bump_triggers_rescan(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    opportunity = make_opportunity(db, AGE_18)
    db.commit()
    scan_catalog(db)
    db.refresh(opportunity)
    stale = scan_catalog(db)
    assert stale.refreshed == 0  # already current

    import app.services.requirement_candidates as module

    monkeypatch.setattr(module, "EXTRACTOR_VERSION", "2")
    result = scan_catalog(db)
    assert result.refreshed == 1
    assert result.unchanged == 0
