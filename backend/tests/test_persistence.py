"""Models, constraints, and repositories against real PostgreSQL. Synthetic data only."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import (
    EducationLevel,
    EligibilityStatus,
    ExtractionMethod,
    FactCategory,
    OpportunitySourceType,
    OpportunityType,
    ProfileSourceKind,
    RequirementAppliesAt,
    RequirementsAssessmentStatus,
    RequirementType,
)
from app.models import (
    EligibilityRuleResult,
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirement,
    OpportunitySourceRecord,
    Profile,
    ProfileFact,
    ProfileSource,
)
from app.repositories import evaluate_and_save, get_opportunity, latest_evaluation

pytestmark = pytest.mark.postgres

FETCHED = datetime(2040, 10, 1, 12, 0, tzinfo=UTC)


def make_profile(**changes: Any) -> Profile:
    fields: dict[str, Any] = {
        "current_education_level": EducationLevel.HIGH_SCHOOL,
        "current_grade": "12",
        "education_status_as_of": date(2040, 9, 1),
        "expected_graduation_date": date(2041, 6, 10),
        "expected_enrollment_date": date(2041, 8, 25),
        "expected_future_education_level": EducationLevel.UNDERGRADUATE,
        "date_of_birth": date(2023, 6, 20),
        "citizenships": None,
        "location": "Example City",
    }
    return Profile(**(fields | changes))


def make_opportunity(**changes: Any) -> Opportunity:
    fields: dict[str, Any] = {
        "title": "Example Summer Research Program",
        "organization": "Example Institute",
        "opportunity_type": OpportunityType.RESEARCH,
        "application_deadline": date(2041, 2, 1),
        "start_date": date(2041, 6, 20),
        "end_date": date(2041, 8, 1),
    }
    return Opportunity(**(fields | changes))


def requirement(requirement_type: RequirementType, value: dict[str, Any]) -> OpportunityRequirement:
    return OpportunityRequirement(
        requirement_type=requirement_type,
        value=value,
        extraction_method=ExtractionMethod.MANUAL,
        source_text="Synthetic requirement text.",
    )


def assert_rejected(db: Session, row: object) -> None:
    db.add(row)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_profile_round_trip(db: Session) -> None:
    profile = make_profile(citizenships=["US"], work_authorizations=["US"])
    db.add(profile)
    db.flush()
    db.expire_all()

    loaded = db.get(Profile, profile.id)

    assert loaded is not None
    assert isinstance(loaded.id, uuid.UUID)
    assert loaded.current_education_level is EducationLevel.HIGH_SCHOOL
    assert loaded.expected_graduation_date == date(2041, 6, 10)
    assert loaded.citizenships == ["US"]
    assert loaded.created_at.tzinfo is not None


def test_profile_source_and_facts_keep_provenance(db: Session) -> None:
    profile = make_profile()
    source = ProfileSource(
        kind=ProfileSourceKind.RESUME,
        original_filename="synthetic-resume.pdf",
        storage_ref="private://example/ref",
        content_sha256="0" * 64,
        details={"pages": 1},
    )
    profile.sources.append(source)
    profile.facts += [
        ProfileFact(
            profile_source=source,
            category=FactCategory.SKILL,
            fact_key="python",
            value={"name": "Python"},
            source_kind=ProfileSourceKind.RESUME,
            extraction_method=ExtractionMethod.AI_INFERENCE,
            extractor_name="example-model",
            extractor_version="0",
            confidence=0.7,
        ),
        ProfileFact(
            category=FactCategory.PREFERENCE,
            fact_key="remote",
            value=True,
            source_kind=ProfileSourceKind.MANUAL,
            extraction_method=ExtractionMethod.MANUAL,
            verified_by_user=True,
        ),
    ]
    db.add(profile)
    db.flush()
    db.expire_all()

    facts = db.scalars(select(ProfileFact).where(ProfileFact.profile_id == profile.id)).all()
    inferred = next(f for f in facts if f.extraction_method is ExtractionMethod.AI_INFERENCE)
    manual = next(f for f in facts if f.extraction_method is ExtractionMethod.MANUAL)

    assert inferred.profile_source is not None
    assert inferred.profile_source.kind is ProfileSourceKind.RESUME
    assert inferred.verified_by_user is False  # inferred facts default to unverified
    assert inferred.value == {"name": "Python"}
    assert manual.profile_source_id is None
    assert manual.value is True


def test_deleting_a_profile_removes_its_private_data(db: Session) -> None:
    profile = make_profile()
    source = ProfileSource(kind=ProfileSourceKind.MANUAL)
    profile.sources.append(source)
    profile.facts.append(
        ProfileFact(
            profile_source=source,
            category=FactCategory.SKILL,
            fact_key="k",
            value="v",
            source_kind=ProfileSourceKind.MANUAL,
            extraction_method=ExtractionMethod.MANUAL,
        )
    )
    db.add(profile)
    db.flush()

    db.delete(profile)
    db.flush()

    assert db.scalars(select(ProfileSource)).all() == []
    assert db.scalars(select(ProfileFact)).all() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"education_status_as_of": None},  # level without an as-of date
        {"expected_enrollment_date": date(2041, 1, 1)},  # enrollment before graduation
    ],
)
def test_profile_check_constraints(db: Session, changes: dict[str, Any]) -> None:
    assert_rejected(db, make_profile(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"confidence": 1.5},
        {"confidence": -0.1},
        {"extraction_method": ExtractionMethod.AI_INFERENCE, "extractor_name": None},
    ],
)
def test_profile_fact_check_constraints(db: Session, changes: dict[str, Any]) -> None:
    profile = make_profile()
    db.add(profile)
    db.flush()
    fields: dict[str, Any] = {
        "profile_id": profile.id,
        "category": FactCategory.SKILL,
        "fact_key": "k",
        "value": "v",
        "source_kind": ProfileSourceKind.MANUAL,
        "extraction_method": ExtractionMethod.MANUAL,
    }

    assert_rejected(db, ProfileFact(**(fields | changes)))


def test_foreign_keys_are_enforced(db: Session) -> None:
    assert_rejected(db, ProfileSource(profile_id=uuid.uuid4(), kind=ProfileSourceKind.MANUAL))


def test_opportunity_with_requirements_and_sources_round_trip(db: Session) -> None:
    opp = make_opportunity()
    opp.requirements.append(requirement(RequirementType.MINIMUM_AGE, {"years": 16}))
    opp.source_records += [
        OpportunitySourceRecord(
            source_name="example-ats",
            source_type=OpportunitySourceType.ATS,
            external_id="job-1",
            source_url="https://ats.example/jobs/1",
            raw_payload={"id": "job-1", "title": "Example"},
            fetched_at=FETCHED,
        ),
        OpportunitySourceRecord(
            source_name="manual",
            source_type=OpportunitySourceType.MANUAL,
            fetched_at=FETCHED,
        ),
    ]
    db.add(opp)
    db.flush()
    db.expire_all()

    loaded = get_opportunity(db, opp.id)

    assert loaded is not None
    assert loaded.title == "Example Summer Research Program"
    assert [r.value for r in loaded.requirements] == [{"years": 16}]
    assert loaded.requirements[0].applies_at is RequirementAppliesAt.PROGRAM_START
    assert {s.source_name for s in loaded.source_records} == {"example-ats", "manual"}
    assert get_opportunity(db, uuid.uuid4()) is None


def test_source_external_id_is_unique_per_source(db: Session) -> None:
    first, second = make_opportunity(), make_opportunity()
    for opp in (first, second):
        opp.source_records.append(
            OpportunitySourceRecord(
                source_name="example-ats",
                source_type=OpportunitySourceType.ATS,
                external_id="job-1",
                fetched_at=FETCHED,
            )
        )
    db.add(first)
    db.flush()

    assert_rejected(db, second)


def test_records_without_external_id_do_not_collide(db: Session) -> None:
    opp = make_opportunity()
    for _ in range(2):
        opp.source_records.append(
            OpportunitySourceRecord(
                source_name="manual", source_type=OpportunitySourceType.MANUAL, fetched_at=FETCHED
            )
        )
    db.add(opp)
    db.flush()

    assert len(opp.source_records) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"applies_at": RequirementAppliesAt.EXPLICIT_DATE},  # explicit date without the date
        {"reference_date": date(2041, 1, 1)},  # a date that would be ignored
        {"confidence": 2.0},
    ],
)
def test_requirement_check_constraints(db: Session, changes: dict[str, Any]) -> None:
    opp = make_opportunity()
    db.add(opp)
    db.flush()
    req = requirement(RequirementType.MINIMUM_AGE, {"years": 16})
    for name, value in changes.items():
        setattr(req, name, value)
    req.opportunity_id = opp.id

    assert_rejected(db, req)


def test_requirements_assessment_defaults_to_unassessed(db: Session) -> None:
    orm_default = make_opportunity()
    db.add(orm_default)
    # Server default: a row inserted without the column, as a raw-SQL importer would.
    server_default_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO opportunities (id, title, organization, opportunity_type)"
            " VALUES (:id, 'Example', 'Example Org', 'internship')"
        ),
        {"id": server_default_id},
    )
    db.flush()
    db.expire_all()

    for opportunity_id in (orm_default.id, server_default_id):
        loaded = db.get(Opportunity, opportunity_id)
        assert loaded is not None
        assert loaded.requirements_assessment_status is RequirementsAssessmentStatus.UNASSESSED


@pytest.mark.parametrize("assessment", list(RequirementsAssessmentStatus))
def test_requirements_assessment_round_trip(
    db: Session, assessment: RequirementsAssessmentStatus
) -> None:
    opp = make_opportunity(requirements_assessment_status=assessment)
    db.add(opp)
    db.flush()
    db.expire_all()

    loaded = db.get(Opportunity, opp.id)

    assert loaded is not None and loaded.requirements_assessment_status is assessment


def test_requirements_assessment_is_checked_by_the_database(db: Session) -> None:
    opp = make_opportunity()
    db.add(opp)
    db.flush()

    with pytest.raises(IntegrityError):
        db.connection().exec_driver_sql(
            "UPDATE opportunities SET requirements_assessment_status = 'done' WHERE id = %s",
            (opp.id,),
        )
    db.rollback()


def test_opportunity_date_order_constraint(db: Session) -> None:
    assert_rejected(db, make_opportunity(end_date=date(2041, 6, 1)))


def test_enum_values_are_checked_by_the_database(db: Session) -> None:
    profile = make_profile()
    db.add(profile)
    db.flush()

    with pytest.raises(IntegrityError):
        db.connection().exec_driver_sql(
            "UPDATE profiles SET current_education_level = 'kindergarten' WHERE id = %s",
            (profile.id,),
        )
    db.rollback()


def test_evaluation_is_persisted_with_rule_results(db: Session) -> None:
    profile = make_profile()
    opp = make_opportunity(requirements_assessment_status=RequirementsAssessmentStatus.COMPLETE)
    opp.requirements += [
        requirement(RequirementType.MINIMUM_AGE, {"years": 16}),
        requirement(
            RequirementType.EDUCATION, {"levels": ["undergraduate"], "accepts_incoming": True}
        ),
        requirement(RequirementType.CITIZENSHIP, {"countries": ["US"]}),
    ]
    db.add_all([profile, opp])
    db.flush()

    saved = evaluate_and_save(db, profile, opp)
    db.expire_all()
    loaded = latest_evaluation(db, profile.id, opp.id)

    assert loaded is not None and loaded.id == saved.id
    assert loaded.eligibility_status is EligibilityStatus.NEEDS_VERIFICATION  # citizenship unset
    assert loaded.eligibility_rules_version == "v1"
    assert loaded.depends_on_projected_status is False
    assert [r.rule_id for r in loaded.rule_results] == [
        "ELIG-REQ-000",
        "ELIG-AGE-001",
        "ELIG-EDU-001",
        "ELIG-CIT-001",
    ]
    assert loaded.rule_results[0].requirement_id is None
    assert loaded.rule_results[0].status is EligibilityStatus.ELIGIBLE
    edu = loaded.rule_results[2]
    assert edu.status is EligibilityStatus.ELIGIBLE
    assert edu.depends_on_projected_status
    assert edu.reference_date == date(2041, 6, 20)
    assert edu.requirement_id == opp.requirements[1].id
    assert edu.details is not None and edu.details["phase"] == "incoming"


def test_unassessed_opportunity_without_requirements_is_saved_as_needs_verification(
    db: Session,
) -> None:
    profile = make_profile(citizenships=["US"])
    opp = make_opportunity()
    db.add_all([profile, opp])
    db.flush()

    evaluate_and_save(db, profile, opp)
    db.expire_all()
    loaded = latest_evaluation(db, profile.id, opp.id)

    assert loaded is not None
    assert loaded.eligibility_status is EligibilityStatus.NEEDS_VERIFICATION
    [result] = loaded.rule_results
    assert result.rule_id == "ELIG-REQ-000"
    assert result.requirement_id is None
    assert result.details == {"requirements_assessment_status": "unassessed"}


def test_reevaluation_keeps_history_and_latest_wins(db: Session) -> None:
    profile = make_profile()
    opp = make_opportunity(requirements_assessment_status=RequirementsAssessmentStatus.COMPLETE)
    opp.requirements.append(requirement(RequirementType.CITIZENSHIP, {"countries": ["US"]}))
    db.add_all([profile, opp])
    db.flush()

    first = evaluate_and_save(db, profile, opp)
    profile.citizenships = ["US"]
    second = evaluate_and_save(db, profile, opp)

    history = db.scalars(select(OpportunityEvaluation)).all()
    latest = latest_evaluation(db, profile.id, opp.id)
    assert {e.id for e in history} == {first.id, second.id}
    assert latest is not None and latest.id == second.id
    assert latest.eligibility_status is EligibilityStatus.ELIGIBLE


def test_latest_evaluation_breaks_timestamp_ties_deterministically(db: Session) -> None:
    profile = make_profile()
    opp = make_opportunity()
    db.add_all([profile, opp])
    db.flush()
    evaluations = [evaluate_and_save(db, profile, opp) for _ in range(3)]
    for evaluation in evaluations:
        evaluation.evaluated_at = FETCHED
    db.flush()

    latest = latest_evaluation(db, profile.id, opp.id)

    assert latest is not None and latest.id == max(e.id for e in evaluations)


def test_deleting_a_requirement_keeps_rule_results(db: Session) -> None:
    profile = make_profile()
    opp = make_opportunity()
    opp.requirements.append(requirement(RequirementType.MINIMUM_AGE, {"years": 16}))
    db.add_all([profile, opp])
    db.flush()
    evaluation = evaluate_and_save(db, profile, opp)

    db.delete(opp.requirements[0])
    db.flush()
    db.expire_all()

    result = db.scalars(
        select(EligibilityRuleResult).where(
            EligibilityRuleResult.evaluation_id == evaluation.id,
            EligibilityRuleResult.rule_id == "ELIG-AGE-001",
        )
    ).one()
    assert result.requirement_id is None
    assert result.rule_id == "ELIG-AGE-001"
