"""Requirement candidate review API (ADR-012 §7): discovery, accept/edit/reject, completeness,
and automatic evaluation. Synthetic data only.

Candidates are created directly through the ORM (Agent 2's extractor/candidate service isn't in
this worktree); `semantic_key` is computed the same way the service would.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import (
    FactReviewState,
    RequirementAppliesAt,
    RequirementType,
)
from app.models import (
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirement,
    OpportunityRequirementCandidate,
)
from app.opportunities.requirements.identity import semantic_key
from tests.test_api_workflow import AGE_16, count, create, opportunity, put_profile

pytestmark = pytest.mark.postgres

EXTRACTOR_NAME = "requirements-rules"
EXTRACTOR_VERSION = "1"


def add_candidate(
    db: Session,
    opportunity_id: Any,
    *,
    requirement_type: RequirementType = RequirementType.MINIMUM_AGE,
    value: dict[str, Any] | None = None,
    applies_at: RequirementAppliesAt = RequirementAppliesAt.PROGRAM_START,
    reference_date: Any = None,
    review_state: FactReviewState = FactReviewState.PENDING,
    source_text: str = "Applicants must be at least 16 years old.",
    accepted_requirement_id: Any = None,
) -> OpportunityRequirementCandidate:
    value = value if value is not None else {"years": 16}
    candidate = OpportunityRequirementCandidate(
        opportunity_id=opportunity_id,
        semantic_key=semantic_key(requirement_type, value, applies_at, reference_date),
        requirement_type=requirement_type,
        value=value,
        applies_at=applies_at,
        reference_date=reference_date,
        source_text=source_text,
        extractor_name=EXTRACTOR_NAME,
        extractor_version=EXTRACTOR_VERSION,
        review_state=review_state,
        accepted_requirement_id=accepted_requirement_id,
    )
    db.add(candidate)
    db.commit()
    return candidate


def review_url(opportunity_id: str) -> str:
    return f"/api/opportunities/{opportunity_id}/requirement-review"


# --- Auth and CSRF -------------------------------------------------------------------------


def test_requires_auth(anon_client: TestClient, db: Session) -> None:
    created_id = "00000000-0000-0000-0000-000000000000"
    assert anon_client.get(review_url(created_id)).status_code == 401
    assert anon_client.post(f"{review_url(created_id)}/refresh").status_code == 401
    assert anon_client.post(review_url(created_id), json={"reject": []}).status_code == 401


def test_requires_csrf(client: TestClient) -> None:
    created = create(client)
    client.headers.pop("X-CSRF-Token")

    assert client.post(review_url(created["id"]), json={"reject": []}).status_code == 403


# --- Discovery ------------------------------------------------------------------------------


def test_pending_candidates_never_alter_eligibility(client: TestClient, db: Session) -> None:
    put_profile(client)
    created = create(client, requirements=[AGE_16])
    before_evaluation = created["latest_evaluation"]

    add_candidate(db, created["id"])
    response = client.get(review_url(created["id"]))

    assert response.status_code == 200
    body = response.json()
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["review_state"] == "pending"
    # Fetching the review never evaluates; the opportunity's own evaluation is untouched.
    detail = client.get(f"/api/opportunities/{created['id']}").json()
    assert detail["latest_evaluation"]["id"] == before_evaluation["id"]
    assert (
        detail["latest_evaluation"]["eligibility_status"] == before_evaluation["eligibility_status"]
    )


def test_unknown_opportunity_404(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(review_url(missing)).status_code == 404
    assert client.post(f"{review_url(missing)}/refresh").status_code == 404
    assert client.post(review_url(missing), json={"reject": []}).status_code == 404


# --- Accept / edit / reject -----------------------------------------------------------------


def test_accept_one_creates_one_requirement_and_evaluates_once(
    client: TestClient, db: Session
) -> None:
    put_profile(client)
    created = create(client)
    candidate = add_candidate(db, created["id"])
    evaluations_before = count(db, OpportunityEvaluation)

    response = client.post(review_url(created["id"]), json={"accept": [{"id": str(candidate.id)}]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["evaluated"] is True
    assert len(body["review"]["requirements"]) == 1
    [requirement] = body["review"]["requirements"]
    assert requirement["value"] == {"years": 16}
    assert requirement["extraction_method"] == "deterministic_parser"
    assert requirement["extractor_name"] == EXTRACTOR_NAME
    assert requirement["extractor_version"] == EXTRACTOR_VERSION
    assert count(db, OpportunityRequirement) == 1
    assert count(db, OpportunityEvaluation) == evaluations_before + 1
    [accepted] = [c for c in body["review"]["candidates"] if c["review_state"] == "accepted"]
    assert accepted["accepted_requirement_id"] == requirement["id"]


def test_accept_five_in_one_batch_evaluates_exactly_once(client: TestClient, db: Session) -> None:
    put_profile(client)
    created = create(client)
    candidates = [
        add_candidate(
            db,
            created["id"],
            requirement_type=RequirementType.OTHER,
            value={"description": f"Requirement {i}"},
        )
        for i in range(5)
    ]
    evaluations_before = count(db, OpportunityEvaluation)

    response = client.post(
        review_url(created["id"]),
        json={"accept": [{"id": str(c.id)} for c in candidates]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["evaluated"] is True
    assert count(db, OpportunityEvaluation) == evaluations_before + 1
    assert count(db, OpportunityRequirement) == 5


def test_reject_only_on_pending_does_not_evaluate(client: TestClient, db: Session) -> None:
    put_profile(client)
    created = create(client)
    candidate = add_candidate(db, created["id"])
    evaluations_before = count(db, OpportunityEvaluation)

    response = client.post(review_url(created["id"]), json={"reject": [str(candidate.id)]})

    assert response.status_code == 200, response.text
    assert response.json()["evaluated"] is False
    assert count(db, OpportunityEvaluation) == evaluations_before
    assert count(db, OpportunityRequirement) == 0
    [rejected] = response.json()["review"]["candidates"]
    assert rejected["review_state"] == "rejected"


def test_edit_and_accept_keeps_candidate_original_value_and_key(
    client: TestClient, db: Session
) -> None:
    created = create(client)
    candidate = add_candidate(db, created["id"])
    original_key = candidate.semantic_key

    response = client.post(
        review_url(created["id"]),
        json={"accept": [{"id": str(candidate.id), "value": {"years": 18}}]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    [requirement] = body["review"]["requirements"]
    assert requirement["value"] == {"years": 18}
    [cand] = body["review"]["candidates"]
    assert cand["value"] == {"years": 16}  # the original proposal, untouched
    db.refresh(candidate)
    assert candidate.semantic_key == original_key


def test_explicit_complete_with_zero_requirements_resolves_unassessed_reason(
    client: TestClient, db: Session
) -> None:
    put_profile(client)
    created = create(client)

    response = client.post(review_url(created["id"]), json={"assessment_status": "complete"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["review"]["requirements_assessment_status"] == "complete"
    assert body["review"]["requirements"] == []
    evaluation = client.get(f"/api/opportunities/{created['id']}").json()["latest_evaluation"]
    [req_000] = [r for r in evaluation["rule_results"] if r["rule_id"] == "ELIG-REQ-000"]
    assert req_000["status"] == "eligible"


def test_reject_all_does_not_imply_complete(client: TestClient, db: Session) -> None:
    created = create(client)
    candidate = add_candidate(db, created["id"])

    response = client.post(review_url(created["id"]), json={"reject": [str(candidate.id)]})

    assert response.status_code == 200, response.text
    assert response.json()["review"]["requirements_assessment_status"] == "unassessed"


def test_accepting_while_unassessed_moves_to_partial(client: TestClient, db: Session) -> None:
    created = create(client)
    candidate = add_candidate(db, created["id"])

    response = client.post(review_url(created["id"]), json={"accept": [{"id": str(candidate.id)}]})

    assert response.json()["review"]["requirements_assessment_status"] == "partial"


def test_reject_accepted_deletes_its_canonical_requirement(client: TestClient, db: Session) -> None:
    created = create(client)
    candidate = add_candidate(db, created["id"])
    client.post(review_url(created["id"]), json={"accept": [{"id": str(candidate.id)}]})
    assert count(db, OpportunityRequirement) == 1

    response = client.post(review_url(created["id"]), json={"reject": [str(candidate.id)]})

    assert response.status_code == 200, response.text
    assert count(db, OpportunityRequirement) == 0
    [rejected] = response.json()["review"]["candidates"]
    assert rejected["review_state"] == "rejected"
    assert rejected["accepted_requirement_id"] is None


def test_stale_cleared_after_successful_review(client: TestClient, db: Session) -> None:
    created = create(client)
    opportunity = db.get(Opportunity, created["id"])
    assert opportunity is not None
    opportunity.requirements_stale_since = datetime.now(UTC) - timedelta(days=1)
    db.commit()
    candidate = add_candidate(db, created["id"])

    response = client.post(review_url(created["id"]), json={"reject": [str(candidate.id)]})

    assert response.status_code == 200, response.text
    assert response.json()["review"]["requirements_stale_since"] is None


def test_404_for_a_candidate_of_another_opportunity(client: TestClient, db: Session) -> None:
    created = create(client)
    other = create(client, title="Another Example Opportunity")
    candidate = add_candidate(db, other["id"])

    response = client.post(review_url(created["id"]), json={"reject": [str(candidate.id)]})

    assert response.status_code == 404


# --- Validation (zero partial mutation) -----------------------------------------------------


def test_empty_batch_is_invalid(client: TestClient) -> None:
    created = create(client)
    assert client.post(review_url(created["id"]), json={}).status_code == 422


def test_duplicate_id_across_accept_and_reject_is_invalid(client: TestClient, db: Session) -> None:
    created = create(client)
    candidate = add_candidate(db, created["id"])

    response = client.post(
        review_url(created["id"]),
        json={"accept": [{"id": str(candidate.id)}], "reject": [str(candidate.id)]},
    )

    assert response.status_code == 422


def test_failed_validation_mutates_nothing(client: TestClient, db: Session) -> None:
    put_profile(client)
    created = create(client)
    good = add_candidate(db, created["id"])
    bad = add_candidate(
        db,
        created["id"],
        requirement_type=RequirementType.MINIMUM_AGE,
        value={"years": 20},
        source_text="Applicants must be at least 20 years old.",
    )
    status_before = created["requirements_assessment_status"]
    requirements_before = count(db, OpportunityRequirement)
    candidates_before = {
        (good.id, good.review_state),
        (bad.id, bad.review_state),
    }
    evaluations_before = count(db, OpportunityEvaluation)

    response = client.post(
        review_url(created["id"]),
        json={
            "accept": [
                {"id": str(good.id)},
                # Not a valid minimum_age value: fails RequirementBody validation.
                {"id": str(bad.id), "value": {"years": "not-a-number"}},
            ]
        },
    )

    assert response.status_code == 422
    db.expire_all()
    opportunity = db.get(Opportunity, created["id"])
    assert opportunity is not None
    assert opportunity.requirements_assessment_status.value == status_before
    assert count(db, OpportunityRequirement) == requirements_before
    assert count(db, OpportunityEvaluation) == evaluations_before
    after = {
        (c.id, c.review_state)
        for c in db.scalars(
            select(OpportunityRequirementCandidate).where(
                OpportunityRequirementCandidate.id.in_([good.id, bad.id])
            )
        ).all()
    }
    assert after == candidates_before


def test_refresh_endpoint_without_candidate_service(client: TestClient) -> None:
    """Agent 2's extractor/candidate service isn't in this worktree; the refresh route still
    exists and 404s for an unknown opportunity, and skips cleanly once the service is present."""
    pytest.importorskip("app.services.requirement_candidates")


# --- Review findings (adversarial pass, 2026-10-02) ------------------------------------------

AGE_18_TEXT = "You must be at least 18."
AGE_18 = {"requirement_type": "minimum_age", "value": {"years": 18}}


def _review(client: TestClient, opportunity_id: str) -> dict[str, Any]:
    response = client.get(review_url(opportunity_id))
    assert response.status_code == 200, response.text
    return response.json()


def _post(client: TestClient, opportunity_id: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(review_url(opportunity_id), json=body)
    assert response.status_code == 200, response.text
    return response.json()["review"]


def _only_candidate(review: dict[str, Any]) -> dict[str, Any]:
    [candidate] = review["candidates"]
    return candidate


def test_form_edit_keeps_accepted_suggestion_linked_so_reject_removes_it(
    client: TestClient,
) -> None:
    """H1: a PUT replaces every requirement row; the accepted suggestion must follow its
    requirement to the new row, or a later reject leaves the requirement in force."""
    created = create(client, description=AGE_18_TEXT)
    candidate = _only_candidate(_review(client, created["id"]))
    _post(client, created["id"], {"accept": [{"id": candidate["id"]}]})

    edited = client.put(
        f"/api/opportunities/{created['id']}",
        json=opportunity(description=AGE_18_TEXT, location="Another City", requirements=[AGE_18]),
    )
    assert edited.status_code == 200, edited.text
    relinked = _only_candidate(_review(client, created["id"]))
    [requirement] = _review(client, created["id"])["requirements"]
    assert relinked["accepted_requirement_id"] == requirement["id"]

    review = _post(client, created["id"], {"reject": [candidate["id"]]})
    assert review["requirements"] == []


def test_form_edit_keeps_an_edited_accept_linked(client: TestClient) -> None:
    created = create(client, description=AGE_18_TEXT)
    candidate = _only_candidate(_review(client, created["id"]))
    _post(client, created["id"], {"accept": [{"id": candidate["id"], "value": {"years": 19}}]})
    edited_requirement = {"requirement_type": "minimum_age", "value": {"years": 19}}
    client.put(
        f"/api/opportunities/{created['id']}",
        json=opportunity(description=AGE_18_TEXT, requirements=[edited_requirement]),
    )

    # Re-editing updates the one linked requirement instead of adding a second.
    review = _post(
        client, created["id"], {"accept": [{"id": candidate["id"], "value": {"years": 20}}]}
    )
    assert [r["value"] for r in review["requirements"]] == [{"years": 20}]


def test_suggestion_already_entered_by_hand_never_duplicates(
    client: TestClient, db: Session
) -> None:
    """H2: a pending suggestion the owner then types by hand is dropped on refresh, and
    accepting an identical suggestion links the existing requirement instead of adding one."""
    created = create(client, description=AGE_18_TEXT)
    assert _only_candidate(_review(client, created["id"]))["review_state"] == "pending"

    client.put(
        f"/api/opportunities/{created['id']}",
        json=opportunity(description=AGE_18_TEXT, requirements=[AGE_18]),
    )
    review = _review(client, created["id"])
    assert review["candidates"] == []
    [requirement] = review["requirements"]

    # A suggestion that slipped in anyway (e.g. written before the edit) links, not duplicates.
    stray = add_candidate(db, created["id"], value={"years": 18})
    review = _post(client, created["id"], {"accept": [{"id": str(stray.id)}]})
    assert [r["id"] for r in review["requirements"]] == [requirement["id"]]
    assert _only_candidate(review)["accepted_requirement_id"] == requirement["id"]


def test_rejecting_an_accepted_requirement_never_keeps_complete(client: TestClient) -> None:
    """L3: completeness was asserted for a set that just lost a requirement."""
    put_profile(client)
    created = create(client, description=AGE_18_TEXT)
    candidate = _only_candidate(_review(client, created["id"]))
    review = _post(
        client,
        created["id"],
        {"accept": [{"id": candidate["id"]}], "assessment_status": "complete"},
    )
    assert review["requirements_assessment_status"] == "complete"

    review = _post(client, created["id"], {"reject": [candidate["id"]]})
    assert review["requirements_assessment_status"] == "unassessed"

    # An explicit assertion in the same batch still wins.
    _post(client, created["id"], {"accept": [{"id": candidate["id"]}]})
    review = _post(
        client, created["id"], {"reject": [candidate["id"]], "assessment_status": "complete"}
    )
    assert review["requirements_assessment_status"] == "complete"
