"""Work-authorization eligibility rules and profile facts (ADR-026). Synthetic data only."""

from collections.abc import Mapping
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.enums import EligibilityStatus, RequirementType
from app.opportunities.eligibility.rules import evaluate_requirement
from app.opportunities.eligibility.schemas import OpportunityInput, ProfileInput, RequirementInput
from app.opportunities.eligibility.work_authorization import LABEL_KINDS
from app.opportunities.requirements import extractor
from tests.test_api_workflow import PROFILE, create, put_profile

OK, NO, NV = (
    EligibilityStatus.ELIGIBLE,
    EligibilityStatus.INELIGIBLE,
    EligibilityStatus.NEEDS_VERIFICATION,
)

AUTHORIZED = extractor.WORK_AUTH_LABEL
NO_SPONSOR = extractor.WORK_AUTH_NO_SPONSORSHIP_LABEL
CITIZEN_OR_PR = extractor.OTHER_CITIZEN_OR_PR_LABEL
US_PERSON = extractor.OTHER_US_PERSON_LABEL
CLEARANCE = extractor.OTHER_SECURITY_CLEARANCE_LABEL

FACTS = (
    "work_authorized_us",
    "needs_sponsorship_now",
    "needs_sponsorship_future",
    "us_citizen",
    "us_permanent_resident",
    "us_person_export_control",
    "active_security_clearance",
)

WA, OTHER = RequirementType.WORK_AUTHORIZATION, RequirementType.OTHER


def run(label: str, rtype: RequirementType, **facts: bool | None) -> tuple[str, EligibilityStatus]:
    requirement = RequirementInput(requirement_type=rtype, value={"description": label})
    result = evaluate_requirement(
        ProfileInput.model_validate(facts), OpportunityInput(), requirement
    )
    return result.rule_id, result.status


def test_label_map_matches_the_extractor_constants() -> None:
    assert set(LABEL_KINDS) == {AUTHORIZED, NO_SPONSOR, CITIZEN_OR_PR, US_PERSON, CLEARANCE}


NO_SPONSOR_ALL = {
    "work_authorized_us": True,
    "needs_sponsorship_now": False,
    "needs_sponsorship_future": False,
}


Case = tuple[str, RequirementType, Mapping[str, bool | None], str, EligibilityStatus]
CASES: list[Case] = [
    # ELIG-WA-001: needs an explicit "yes"; "no" is never ineligible (it may change)
    (AUTHORIZED, WA, {"work_authorized_us": True}, "ELIG-WA-001", OK),
    (AUTHORIZED, WA, {"work_authorized_us": False}, "ELIG-WA-001", NV),
    (AUTHORIZED, WA, {}, "ELIG-WA-001", NV),
    # ELIG-WA-002
    (NO_SPONSOR, WA, NO_SPONSOR_ALL, "ELIG-WA-002", OK),
    (NO_SPONSOR, WA, {"needs_sponsorship_now": True}, "ELIG-WA-002", NO),
    (NO_SPONSOR, WA, NO_SPONSOR_ALL | {"needs_sponsorship_future": None}, "ELIG-WA-002", NV),
    (NO_SPONSOR, WA, NO_SPONSOR_ALL | {"needs_sponsorship_future": True}, "ELIG-WA-002", NV),
    (NO_SPONSOR, WA, NO_SPONSOR_ALL | {"work_authorized_us": None}, "ELIG-WA-002", NV),
    (NO_SPONSOR, WA, NO_SPONSOR_ALL | {"work_authorized_us": False}, "ELIG-WA-002", NV),
    (NO_SPONSOR, WA, {}, "ELIG-WA-002", NV),
    # ELIG-WA-003: reads the two facts; one explicit yes is enough
    (CITIZEN_OR_PR, OTHER, {"us_citizen": True}, "ELIG-WA-003", OK),
    (CITIZEN_OR_PR, OTHER, {"us_permanent_resident": True}, "ELIG-WA-003", OK),
    (
        CITIZEN_OR_PR,
        OTHER,
        {"us_citizen": False, "us_permanent_resident": False},
        "ELIG-WA-003",
        NO,
    ),
    (CITIZEN_OR_PR, OTHER, {"us_citizen": False}, "ELIG-WA-003", NV),
    (CITIZEN_OR_PR, OTHER, {}, "ELIG-WA-003", NV),
    # ELIG-WA-004
    (US_PERSON, OTHER, {"us_person_export_control": True}, "ELIG-WA-004", OK),
    (US_PERSON, OTHER, {"us_person_export_control": False}, "ELIG-WA-004", NO),
    (US_PERSON, OTHER, {}, "ELIG-WA-004", NV),
    # ELIG-WA-005: never ineligible (the posting may allow obtaining one)
    (CLEARANCE, OTHER, {"active_security_clearance": True}, "ELIG-WA-005", OK),
    (CLEARANCE, OTHER, {"active_security_clearance": False}, "ELIG-WA-005", NV),
    (CLEARANCE, OTHER, {}, "ELIG-WA-005", NV),
]


@pytest.mark.parametrize(("label", "rtype", "facts", "rule_id", "status"), CASES)
def test_rule_outcomes(
    label: str,
    rtype: RequirementType,
    facts: Mapping[str, bool | None],
    rule_id: str,
    status: EligibilityStatus,
) -> None:
    assert run(label, rtype, **facts) == (rule_id, status)


@pytest.mark.parametrize(
    ("label", "rtype", "own_facts"),
    [
        (AUTHORIZED, WA, {"work_authorized_us"}),
        (US_PERSON, OTHER, {"us_person_export_control"}),
        (CLEARANCE, OTHER, {"active_security_clearance"}),
        (CITIZEN_OR_PR, OTHER, {"us_citizen", "us_permanent_resident"}),
    ],
)
def test_no_cross_inference(label: str, rtype: RequirementType, own_facts: set[str]) -> None:
    """Every other fact being "yes" never satisfies a rule whose own facts aren't provided."""
    others = {name: True for name in FACTS if name not in own_facts}
    assert run(label, rtype, **others)[1] is NV


def test_citizen_does_not_mean_authorized_or_us_person() -> None:
    citizen = {"us_citizen": True, "us_permanent_resident": True}
    assert run(AUTHORIZED, WA, **citizen)[1] is NV
    assert run(US_PERSON, OTHER, **citizen)[1] is NV
    assert run(NO_SPONSOR, WA, **citizen)[1] is NV


def test_not_a_citizen_is_not_ineligible_for_other_rules() -> None:
    assert run(US_PERSON, OTHER, us_citizen=False, us_permanent_resident=False)[1] is NV
    assert run(CLEARANCE, OTHER, us_citizen=False)[1] is NV


@pytest.mark.parametrize(
    ("rtype", "value"),
    [
        (WA, {"description": "US work auth"}),  # free text: no explicit kind
        (WA, {"description": AUTHORIZED.lower()}),  # edited wording
        (OTHER, {"description": "Essay required"}),
        (WA, {"countries": ["US"]}),
        (OTHER, {"description": 5}),
    ],
)
def test_requirement_without_explicit_kind_stays_needs_verification(
    rtype: RequirementType, value: dict[str, Any]
) -> None:
    everything = ProfileInput.model_validate(dict.fromkeys(FACTS, True))
    result = evaluate_requirement(
        everything, OpportunityInput(), RequirementInput(requirement_type=rtype, value=value)
    )
    assert (result.rule_id, result.status) == ("ELIG-REQ-001", NV)


def test_citizenship_requirement_still_reads_only_citizenships() -> None:
    requirement = RequirementInput(
        requirement_type=RequirementType.CITIZENSHIP, value={"countries": ["US"]}
    )
    result = evaluate_requirement(
        ProfileInput.model_validate({"us_citizen": True}), OpportunityInput(), requirement
    )
    assert (result.rule_id, result.status) == ("ELIG-CIT-001", NV)


# --- Profile API and re-evaluation ------------------------------------------------------------


@pytest.mark.postgres
def test_profile_facts_default_to_not_provided_and_round_trip(client: TestClient) -> None:
    saved = put_profile(client)["profile"]
    assert all(saved[name] is None for name in FACTS)

    saved = put_profile(client, us_citizen=True, work_authorized_us=False)["profile"]
    read = client.get("/api/profile").json()
    assert read["us_citizen"] is True and read["work_authorized_us"] is False
    assert read["us_permanent_resident"] is None  # untouched answers stay "not provided"
    assert saved == read


@pytest.mark.postgres
@pytest.mark.parametrize("value", ["yes", 1, "true", []])
def test_profile_fact_validation_is_strict(client: TestClient, value: Any) -> None:
    response = client.put("/api/profile", json=PROFILE | {"us_person_export_control": value})
    assert response.status_code == 422


@pytest.mark.postgres
def test_facts_drive_evaluation_and_changes_reevaluate(client: TestClient) -> None:
    put_profile(client)
    created = create(
        client,
        requirements_assessment_status="complete",
        requirements=[{"requirement_type": "other", "value": {"description": US_PERSON}}],
    )
    evaluation = created["latest_evaluation"]
    assert evaluation["eligibility_status"] == "needs_verification"
    assert evaluation["rule_results"][1]["rule_id"] == "ELIG-WA-004"

    def latest() -> dict[str, Any]:
        return client.get(f"/api/opportunities/{created['id']}").json()["latest_evaluation"]

    # A citizen answer is not a U.S.-person answer.
    put_profile(client, us_citizen=True)
    assert latest()["eligibility_status"] == "needs_verification"

    saved = put_profile(client, us_citizen=True, us_person_export_control=True)
    assert saved["reevaluated_opportunities"] == 1
    assert latest()["eligibility_status"] == "eligible"
    assert latest()["eligibility_rules_version"] == "v2"

    put_profile(client, us_citizen=True, us_person_export_control=False)
    assert latest()["eligibility_status"] == "ineligible"


@pytest.mark.postgres
def test_a_body_without_the_answers_keeps_them(client: TestClient) -> None:
    put_profile(client, us_citizen=True, needs_sponsorship_now=False)
    response = client.put("/api/profile", json=PROFILE)  # an older client omits the answers
    assert response.status_code == 200
    read = client.get("/api/profile").json()
    assert read["us_citizen"] is True and read["needs_sponsorship_now"] is False
    # An explicit null still clears an answer.
    assert put_profile(client, us_citizen=None)["profile"]["us_citizen"] is None
