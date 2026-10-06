"""Profile, manual opportunity, evaluation, and application-tracking API. Synthetic data only.

The synthetic profile is a high-school senior expected to graduate 2041-06-10 and enroll as an
undergraduate 2041-08-25 (fictional dates, as in docs/eligibility.md).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Application,
    EligibilityRuleResult,
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirement,
    OpportunitySourceRecord,
)
from app.services import opportunities as opportunity_service

pytestmark = pytest.mark.postgres

PROFILE: dict[str, Any] = {
    "current_education_level": "high_school",
    "current_grade": "12",
    "education_status_as_of": "2040-09-01",
    "expected_graduation_date": "2041-06-10",
    "expected_enrollment_date": "2041-08-25",
    "expected_future_education_level": "undergraduate",
    "date_of_birth": "2023-06-20",
    "citizenships": None,
    "work_authorizations": None,
    "location": "Example City",
}

AGE_16 = {"requirement_type": "minimum_age", "value": {"years": 16}}
INCOMING_UNDERGRAD = {
    "requirement_type": "education",
    "value": {"levels": ["undergraduate"], "accepts_incoming": True},
}
US_CITIZENS = {"requirement_type": "citizenship", "value": {"countries": ["US"]}}


def opportunity(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Example Summer Research Program",
        "organization": "Example Institute",
        "opportunity_type": "research",
        "description": "Synthetic description.",
        "application_url": "https://example.org/apply",
        "location": "Example City",
        "remote_mode": "onsite",
        "application_deadline": "2041-02-01",
        "start_date": "2041-06-20",
        "end_date": "2041-08-01",
        "requirements": [],
    }
    return body | changes


def count(db: Session, model: type[Any]) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def put_profile(client: TestClient, **changes: Any) -> dict[str, Any]:
    response = client.put("/api/profile", json=PROFILE | changes)
    assert response.status_code == 200, response.text
    return response.json()


def create(client: TestClient, **changes: Any) -> dict[str, Any]:
    response = client.post("/api/opportunities", json=opportunity(**changes))
    assert response.status_code == 201, response.text
    return response.json()


# --- Profile -----------------------------------------------------------------------------------


def test_profile_is_created_read_and_replaced(client: TestClient) -> None:
    assert client.get("/api/profile").status_code == 404

    saved = put_profile(client, citizenships=["us", "CA", "US"])
    read = client.get("/api/profile").json()

    assert saved["profile"] == read
    assert read["citizenships"] == ["US", "CA"]  # normalized and de-duplicated
    assert read["current_grade"] == "12"
    assert saved["reevaluated_opportunities"] == 0  # nothing to evaluate yet

    replaced = put_profile(client, location="  ", current_grade=None)["profile"]
    assert replaced["id"] == read["id"]  # still the single profile
    assert replaced["location"] is None
    assert replaced["current_grade"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"citizenships": ["UK"]},  # not an ISO 3166-1 code (GB is)
        {"citizenships": ["USA"]},
        {"work_authorizations": ["ZZ"]},
        {"education_status_as_of": None},  # level without its as-of date
        {"expected_enrollment_date": "2041-01-01"},  # before graduation
        {"date_of_birth": "2999-01-01"},
        {"current_education_level": "kindergarten"},
        {"current_grade": "x" * 33},
        {"unexpected_field": 1},
    ],
)
def test_profile_validation(client: TestClient, changes: dict[str, Any]) -> None:
    response = client.put("/api/profile", json=PROFILE | changes)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize(
    "status_as_of",
    ["2041-09-01", "2041-06-10"],  # after, and on, the expected graduation
)
def test_profile_rejects_status_recorded_after_graduation(
    client: TestClient, status_as_of: str
) -> None:
    body = PROFILE | {
        "education_status_as_of": status_as_of,
        "expected_graduation_date": "2041-06-10",
    }
    response = client.put("/api/profile", json=body)

    assert response.status_code == 422
    [issue] = response.json()["detail"]
    assert "expected_graduation_date must be after education_status_as_of" in issue["msg"]
    assert client.get("/api/profile").status_code == 404  # nothing was saved


def test_profile_accepts_status_the_day_before_graduation(client: TestClient) -> None:
    body = PROFILE | {
        "education_status_as_of": "2041-06-09",
        "expected_graduation_date": "2041-06-10",
    }
    saved = put_profile(client, **body)["profile"]

    assert saved["education_status_as_of"] == "2041-06-09"


# --- Opportunities -----------------------------------------------------------------------------


def test_manual_opportunity_keeps_provenance_and_structured_requirements(
    client: TestClient, db: Session
) -> None:
    created = create(client, requirements=[AGE_16 | {"source_text": "Must be 16."}])

    [source] = db.scalars(select(OpportunitySourceRecord)).all()
    assert str(source.opportunity_id) == created["id"]
    assert source.source_type == "manual"
    assert source.source_name == "manual"
    assert source.external_id is None
    assert source.raw_payload is None
    [requirement] = created["requirements"]
    assert requirement["value"] == {"years": 16}
    assert requirement["applies_at"] == "program_start"
    assert requirement["extraction_method"] == "manual"
    assert requirement["source_text"] == "Must be 16."
    assert created["requirements_assessment_status"] == "unassessed"
    assert created["application"] is None


def test_without_a_profile_nothing_is_evaluated(client: TestClient, db: Session) -> None:
    created = create(client, requirements=[AGE_16])

    assert created["profile_exists"] is False
    assert created["latest_evaluation"] is None
    assert count(db, OpportunityEvaluation) == 0
    [summary] = client.get("/api/opportunities").json()["items"]
    assert summary["eligibility_status"] is None
    assert client.post(f"/api/opportunities/{created['id']}/evaluate").status_code == 409


def test_new_opportunity_is_evaluated_and_unassessed_needs_verification(
    client: TestClient,
) -> None:
    put_profile(client)

    evaluation = create(client, requirements=[AGE_16])["latest_evaluation"]

    assert evaluation["eligibility_status"] == "needs_verification"
    assert evaluation["eligibility_rules_version"] == "v2"
    assert [r["rule_id"] for r in evaluation["rule_results"]] == ["ELIG-REQ-000", "ELIG-AGE-001"]
    assert evaluation["rule_results"][1]["status"] == "eligible"


def test_complete_requirements_can_be_eligible_via_projected_status(client: TestClient) -> None:
    put_profile(client)

    created = create(
        client,
        requirements_assessment_status="complete",
        requirements=[AGE_16, INCOMING_UNDERGRAD],
    )

    evaluation = created["latest_evaluation"]
    assert evaluation["eligibility_status"] == "eligible"
    assert evaluation["depends_on_projected_status"] is True
    education = evaluation["rule_results"][2]
    assert education["rule_id"] == "ELIG-EDU-001"
    assert education["depends_on_projected_status"] is True
    assert education["details"]["phase"] == "incoming"
    assert education["requirement_id"] == created["requirements"][1]["id"]


def test_unsupported_requirement_types_are_stored_but_need_verification(
    client: TestClient,
) -> None:
    put_profile(client)

    created = create(
        client,
        requirements_assessment_status="complete",
        requirements=[
            {"requirement_type": "work_authorization", "value": {"description": "US work auth"}},
            {"requirement_type": "other", "value": {"description": "Essay required"}},
        ],
    )

    evaluation = created["latest_evaluation"]
    assert evaluation["eligibility_status"] == "needs_verification"
    assert [r["rule_id"] for r in evaluation["rule_results"]][1:] == [
        "ELIG-REQ-001",
        "ELIG-REQ-001",
    ]
    assert created["requirements"][0]["value"] == {"description": "US work auth"}


def test_update_replaces_requirements_and_appends_history(client: TestClient, db: Session) -> None:
    put_profile(client)
    created = create(client, requirements=[US_CITIZENS])
    old_requirement_id = created["requirements"][0]["id"]

    response = client.put(
        f"/api/opportunities/{created['id']}",
        json=opportunity(
            title="Renamed Synthetic Program",
            requirements_assessment_status="complete",
            requirements=[AGE_16],
        ),
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Renamed Synthetic Program"
    assert [r["value"] for r in updated["requirements"]] == [{"years": 16}]
    assert updated["latest_evaluation"]["eligibility_status"] == "eligible"
    assert count(db, OpportunityEvaluation) == 2  # history kept
    assert count(db, OpportunityRequirement) == 1
    # The old evaluation's explanation survives the requirement's deletion.
    old_results = db.scalars(
        select(EligibilityRuleResult).where(EligibilityRuleResult.rule_id == "ELIG-CIT-001")
    ).all()
    assert len(old_results) == 1 and old_results[0].requirement_id is None
    assert old_requirement_id not in {r["id"] for r in updated["requirements"]}


def test_list_shows_latest_status_and_tracking(client: TestClient) -> None:
    put_profile(client)
    first = create(client, title="First Synthetic")
    second = create(client, title="Second Synthetic", requirements_assessment_status="complete")
    client.put(f"/api/opportunities/{first['id']}/application", json={"status": "saved"})

    listed = {o["title"]: o for o in client.get("/api/opportunities").json()["items"]}

    assert listed["First Synthetic"]["eligibility_status"] == "needs_verification"
    assert listed["First Synthetic"]["application_status"] == "saved"
    assert listed["Second Synthetic"]["eligibility_status"] == "eligible"
    assert listed["Second Synthetic"]["application_status"] is None
    assert listed["Second Synthetic"]["id"] == second["id"]
    assert listed["Second Synthetic"]["evaluated_at"] is not None
    assert set(listed["First Synthetic"]) == {
        "dismissed_at",
        "id",
        "title",
        "organization",
        "opportunity_type",
        "location",
        "remote_mode",
        "application_deadline",
        "start_date",
        "posted_at",
        "first_seen_at",
        "requirements_assessment_status",
        "eligibility_status",
        "evaluated_at",
        "fit_score",
        "scoring_version",
        "fit_coverage",
        "fit_components",
        "application_status",
        "origin",
        "availability",
        "source_names",
        "pending_requirement_count",
        "requirements_stale",
        # ADR-014 §6 (program registry date trust)
        "program_cycle",
        "typical_open_window",
        "typical_close_window",
        "verify_by",
        "needs_date_verification",
        "freshness",
        "freshness_checked_at",
        "program_last_verified",
    }
    assert listed["First Synthetic"]["origin"] == "manual"
    assert listed["First Synthetic"]["availability"] == "manual"
    assert listed["First Synthetic"]["source_names"] == ["Manual entry"]


def test_list_uses_the_latest_evaluation(client: TestClient) -> None:
    put_profile(client)
    created = create(client, requirements_assessment_status="complete", requirements=[US_CITIZENS])
    assert created["latest_evaluation"]["eligibility_status"] == "needs_verification"

    put_profile(client, citizenships=["US"])

    [summary] = client.get("/api/opportunities").json()["items"]
    assert summary["eligibility_status"] == "eligible"


def test_delete_removes_the_opportunity_and_its_data(client: TestClient, db: Session) -> None:
    put_profile(client)
    created = create(client, requirements=[AGE_16])
    client.put(f"/api/opportunities/{created['id']}/application", json={"status": "applied"})

    assert client.delete(f"/api/opportunities/{created['id']}").status_code == 204

    assert client.get(f"/api/opportunities/{created['id']}").status_code == 404
    for model in (
        Opportunity,
        OpportunityRequirement,
        OpportunitySourceRecord,
        OpportunityEvaluation,
        Application,
    ):
        assert count(db, model) == 0, model


def test_unknown_and_malformed_ids(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"

    assert client.get(f"/api/opportunities/{missing}").status_code == 404
    assert client.put(f"/api/opportunities/{missing}", json=opportunity()).status_code == 404
    assert client.delete(f"/api/opportunities/{missing}").status_code == 404
    assert client.get("/api/opportunities/not-a-uuid").status_code == 422


INVALID_OPPORTUNITY_CHANGES: list[dict[str, Any]] = [
    {"title": ""},
    {"opportunity_type": "job"},
    {"application_url": "javascript:alert(1)"},
    {"application_url": "ftp://example.org/file"},
    {"end_date": "2041-06-01"},  # before start
    {"requirements": [{"requirement_type": "minimum_age", "value": {"years": "old"}}]},
    {"requirements": [{"requirement_type": "minimum_age", "value": {"years": 16, "x": 1}}]},
    {"requirements": [{"requirement_type": "education", "value": {"levels": []}}]},
    {"requirements": [{"requirement_type": "citizenship", "value": {"countries": ["XX"]}}]},
    {"requirements": [AGE_16 | {"applies_at": "explicit_date"}]},  # date missing
    {"requirements": [AGE_16 | {"reference_date": "2041-01-01"}]},  # date ignored
    {"requirements": [{"requirement_type": "salary", "value": {}}]},
]


@pytest.mark.parametrize("changes", INVALID_OPPORTUNITY_CHANGES)
def test_opportunity_validation(client: TestClient, changes: dict[str, Any]) -> None:
    assert client.post("/api/opportunities", json=opportunity(**changes)).status_code == 422


def test_citizenship_requirement_codes_are_normalized(client: TestClient) -> None:
    created = create(
        client,
        requirements=[{"requirement_type": "citizenship", "value": {"countries": ["us"]}}],
    )

    assert created["requirements"][0]["value"] == {"countries": ["US"]}


def test_explicit_reference_date_is_used(client: TestClient) -> None:
    put_profile(client)
    created = create(
        client,
        requirements=[AGE_16 | {"applies_at": "explicit_date", "reference_date": "2039-06-19"}],
    )

    age = created["latest_evaluation"]["rule_results"][1]
    assert age["reference_date"] == "2039-06-19"
    assert age["status"] == "ineligible"  # 15 on that date


def test_manual_evaluate_appends_an_evaluation(client: TestClient, db: Session) -> None:
    put_profile(client)
    created = create(client)

    response = client.post(f"/api/opportunities/{created['id']}/evaluate")

    assert response.status_code == 201
    assert response.json()["id"] != created["latest_evaluation"]["id"]
    assert count(db, OpportunityEvaluation) == 2


def test_failed_evaluation_leaves_no_partial_opportunity(
    anon_client: TestClient, client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    put_profile(client)

    def fail(*_: object) -> None:
        raise RuntimeError("synthetic evaluation failure")

    monkeypatch.setattr(opportunity_service, "evaluate_if_changed", fail)
    client_no_raise = TestClient(
        client.app, base_url="https://testserver", raise_server_exceptions=False
    )
    client_no_raise.cookies = client.cookies
    client_no_raise.headers["X-CSRF-Token"] = client.headers["X-CSRF-Token"]

    response = client_no_raise.post("/api/opportunities", json=opportunity(requirements=[AGE_16]))

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    assert "synthetic evaluation failure" not in response.text
    for model in (Opportunity, OpportunityRequirement, OpportunitySourceRecord):
        assert count(db, model) == 0, model


# --- Automatic re-evaluation on profile changes -----------------------------------------------


def test_creating_the_profile_evaluates_existing_opportunities(
    client: TestClient, db: Session
) -> None:
    created = create(client, requirements=[AGE_16])

    saved = put_profile(client)

    assert saved["reevaluated_opportunities"] == 1
    detail = client.get(f"/api/opportunities/{created['id']}").json()
    assert detail["profile_exists"] is True
    assert detail["latest_evaluation"]["eligibility_status"] == "needs_verification"
    assert count(db, OpportunityEvaluation) == 1


def test_eligibility_relevant_profile_change_reevaluates(client: TestClient, db: Session) -> None:
    put_profile(client)
    created = create(client, requirements_assessment_status="complete", requirements=[US_CITIZENS])
    assert created["latest_evaluation"]["eligibility_status"] == "needs_verification"

    saved = put_profile(client, citizenships=["CA"])

    assert saved["reevaluated_opportunities"] == 1
    detail = client.get(f"/api/opportunities/{created['id']}").json()
    assert detail["latest_evaluation"]["eligibility_status"] == "ineligible"
    assert count(db, OpportunityEvaluation) == 2  # appended, not overwritten


@pytest.mark.parametrize(
    "changes",
    [
        {},  # unchanged
        {"location": "Another Example City"},
        {"current_grade": "11"},
        {"work_authorizations": ["US"]},  # stored, but no v1 rule reads it
    ],
)
def test_changes_that_cannot_affect_eligibility_do_not_reevaluate(
    client: TestClient, db: Session, changes: dict[str, Any]
) -> None:
    put_profile(client)
    create(client)

    saved = put_profile(client, **changes)

    assert saved["reevaluated_opportunities"] == 0
    assert count(db, OpportunityEvaluation) == 1


# --- Application tracking ----------------------------------------------------------------------


def test_application_tracking_lifecycle(client: TestClient, db: Session) -> None:
    put_profile(client)
    created = create(client)
    url = f"/api/opportunities/{created['id']}/application"

    started = client.put(url, json={"status": "saved"})
    assert started.status_code == 200
    assert started.json()["status"] == "saved"

    updated = client.put(
        url,
        json={"status": "applied", "submitted_on": "2041-01-20", "notes": "Synthetic note."},
    ).json()
    assert updated["status"] == "applied"
    assert updated["submitted_on"] == "2041-01-20"
    assert updated["notes"] == "Synthetic note."
    assert count(db, Application) == 1  # one row per opportunity

    detail = client.get(f"/api/opportunities/{created['id']}").json()
    assert detail["application"]["status"] == "applied"
    # Tracking never touches eligibility.
    assert count(db, OpportunityEvaluation) == 1

    assert client.delete(url).status_code == 204
    assert client.delete(url).status_code == 404
    assert client.get(f"/api/opportunities/{created['id']}").json()["application"] is None


@pytest.mark.parametrize(
    ("first", "then"),
    [("withdrawn", "saved"), ("rejected", "interview"), ("saved", "accepted")],
)
def test_any_status_transition_is_allowed(client: TestClient, first: str, then: str) -> None:
    url = f"/api/opportunities/{create(client)['id']}/application"
    client.put(url, json={"status": first})

    assert client.put(url, json={"status": then}).json()["status"] == then


@pytest.mark.parametrize(
    "body",
    [{"status": "ghosted"}, {}, {"status": "saved", "notes": "x" * 10_001}],
)
def test_application_validation(client: TestClient, body: dict[str, Any]) -> None:
    url = f"/api/opportunities/{create(client)['id']}/application"

    assert client.put(url, json=body).status_code == 422


def test_application_for_unknown_opportunity_is_404(client: TestClient) -> None:
    url = "/api/opportunities/00000000-0000-0000-0000-000000000000/application"

    assert client.put(url, json={"status": "saved"}).status_code == 404
