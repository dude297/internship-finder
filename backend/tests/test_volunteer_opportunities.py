"""Milestone 7.1: `volunteer` is an ordinary opportunity type. Synthetic data only."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.enums import OpportunityType
from tests.test_api_fit import COMPLETE, put_match
from tests.test_api_workflow import AGE_16, create, opportunity, put_profile

pytestmark = pytest.mark.postgres

TITLE = "Synthetic STEM Tutor Volunteer"


def test_enum_has_volunteer() -> None:
    assert OpportunityType("volunteer") is OpportunityType.VOLUNTEER


def test_create_volunteer_round_trips(client: TestClient) -> None:
    created = create(client, title=TITLE, opportunity_type="volunteer")

    assert created["opportunity_type"] == "volunteer"
    detail = client.get(f"/api/opportunities/{created['id']}").json()
    assert detail["opportunity_type"] == "volunteer"
    items = client.get("/api/opportunities", params={"q": TITLE}).json()["items"]
    assert [i["opportunity_type"] for i in items] == ["volunteer"]


def test_edit_type_to_and_from_volunteer(client: TestClient) -> None:
    created = create(client, title=TITLE, opportunity_type="other")
    url = f"/api/opportunities/{created['id']}"

    to_volunteer = client.put(url, json=opportunity(title=TITLE, opportunity_type="volunteer"))
    assert to_volunteer.status_code == 200, to_volunteer.text
    assert client.get(url).json()["opportunity_type"] == "volunteer"

    to_internship = client.put(url, json=opportunity(title=TITLE, opportunity_type="internship"))
    assert to_internship.status_code == 200, to_internship.text
    assert client.get(url).json()["opportunity_type"] == "internship"


def test_list_reports_each_rows_own_type(client: TestClient) -> None:
    # The list API has no type filter (frozen contract); each row reports its own stored type.
    create(client, title=f"{TITLE} A", opportunity_type="volunteer")
    create(client, title=f"{TITLE} B", opportunity_type="internship")

    items = client.get("/api/opportunities", params={"q": TITLE}).json()["items"]

    assert {i["title"]: i["opportunity_type"] for i in items} == {
        f"{TITLE} A": "volunteer",
        f"{TITLE} B": "internship",
    }


def test_unknown_type_is_still_rejected(client: TestClient) -> None:
    response = client.post("/api/opportunities", json=opportunity(opportunity_type="job"))
    assert response.status_code == 422


def test_type_does_not_affect_eligibility_or_fit(client: TestClient) -> None:
    put_profile(client)  # born 2023-06-20 (fictional dates): age 16 is met
    put_match(client)
    common: dict[str, Any] = {
        "title": "Synthetic Robotics Tutor",
        "description": "Python and SQL for data science on robots.",
        "remote_mode": "hybrid",
        "requirements": [AGE_16],
        **COMPLETE,
    }
    volunteer = create(client, opportunity_type="volunteer", **common)["latest_evaluation"]
    internship = create(client, opportunity_type="internship", **common)["latest_evaluation"]

    def strip(rules: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
        return [(r["rule_id"], r["status"], r["depends_on_projected_status"]) for r in rules]

    assert volunteer["eligibility_status"] == internship["eligibility_status"]
    assert strip(volunteer["rule_results"]) == strip(internship["rule_results"])
    assert any(r["rule_id"] == "ELIG-AGE-001" for r in volunteer["rule_results"])
    assert volunteer["fit_score"] is not None
    assert volunteer["fit_score"] == internship["fit_score"]
    assert volunteer["score_breakdown"] == internship["score_breakdown"]
