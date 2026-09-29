"""Match Profile, fit evaluation, and eligibility-first ranking through the API (ADR-010).
Synthetic data only."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.enums import ExtractionMethod, FactCategory, ProfileSourceKind
from app.models import OpportunityEvaluation, Profile, ProfileFact
from app.repositories import evaluation_context
from app.services import match_profile as match_service
from tests.test_api_workflow import count, create, put_profile

pytestmark = pytest.mark.postgres

MATCH: dict[str, Any] = {
    "skills": ["Python", "SQL"],
    "courses": ["Data Science"],
    "projects": [{"name": "Synthetic Rover", "description": "Python robots with sensors"}],
    "research": [],
    "activities": [{"name": "Synthetic Robotics Club", "description": None}],
    "experience": [],
    "interests": ["robotics"],
    "preferred_locations": ["Example City"],
    "remote_preference": "hybrid_preferred",
    "availability_start": "2041-06-15",
    "availability_end": "2041-08-31",
}
COMPLETE = {"requirements_assessment_status": "complete"}
AGE_99 = {"requirement_type": "minimum_age", "value": {"years": 99}}


def put_match(client: TestClient, **changes: Any) -> dict[str, Any]:
    response = client.put("/api/profile/match", json=MATCH | changes)
    assert response.status_code == 200, response.text
    return response.json()


def ranked(client: TestClient, sort: str = "recommended") -> list[str]:
    response = client.get("/api/opportunities", params={"sort": sort, "limit": 100})
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["items"]]


# --- Match Profile -----------------------------------------------------------------------------


def test_match_profile_starts_empty_and_round_trips(client: TestClient) -> None:
    empty = client.get("/api/profile/match").json()
    assert empty["skills"] == [] and empty["remote_preference"] is None

    saved = put_match(client, skills=[" Python ", "SQL", "Python"])
    assert saved["match_profile"] == MATCH  # trimmed and de-duplicated
    assert client.get("/api/profile/match").json() == MATCH
    # The eligibility profile is untouched and still separate.
    assert client.get("/api/profile").json()["current_education_level"] is None


def test_manual_facts_are_stored_with_provenance(client: TestClient, db: Session) -> None:
    put_match(client)
    facts = db.scalars(select(ProfileFact).order_by(ProfileFact.fact_key)).all()
    assert [(f.category, f.value) for f in facts] == [
        (FactCategory.SKILL, {"name": "Python"}),
        (FactCategory.SKILL, {"name": "SQL"}),
        (FactCategory.COURSE, {"name": "Data Science"}),
        (
            FactCategory.PROJECT,
            {"name": "Synthetic Rover", "description": "Python robots with sensors"},
        ),
        (FactCategory.ACTIVITY, {"name": "Synthetic Robotics Club", "description": None}),
    ]
    for fact in facts:
        assert fact.source_kind is ProfileSourceKind.MANUAL
        assert fact.extraction_method is ExtractionMethod.MANUAL
        assert fact.verified_by_user is True
        assert fact.profile_source_id is None
        assert fact.fact_key.startswith("match_profile.")


def test_save_preserves_facts_it_does_not_own(client: TestClient, db: Session) -> None:
    put_match(client)
    profile = db.scalars(select(Profile)).one()
    others = [
        ProfileFact(
            profile_id=profile.id,
            category=FactCategory.SKILL,
            fact_key="skill",
            value={"name": "Synthetic Parsed Skill"},
            source_kind=ProfileSourceKind.RESUME,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        ),
        ProfileFact(
            profile_id=profile.id,
            category=FactCategory.PROJECT,
            fact_key="project",
            value={"name": "Synthetic Inferred Project"},
            source_kind=ProfileSourceKind.GITHUB,
            extraction_method=ExtractionMethod.AI_INFERENCE,
            extractor_name="synthetic-extractor",
        ),
        ProfileFact(  # manual, but not a Match Profile fact
            profile_id=profile.id,
            category=FactCategory.SKILL,
            fact_key="other_manual_skill",
            value={"name": "Synthetic Other"},
            source_kind=ProfileSourceKind.MANUAL,
            extraction_method=ExtractionMethod.MANUAL,
        ),
    ]
    db.add_all(others)
    db.commit()

    put_match(client, skills=["Rust"], projects=[])

    keys = set(db.scalars(select(ProfileFact.fact_key)).all())
    assert {"skill", "project", "other_manual_skill"} <= keys
    assert client.get("/api/profile/match").json()["skills"] == ["Rust"]


def test_one_save_runs_one_catalog_pass(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    put_profile(client)
    for n in range(3):
        create(client, title=f"Synthetic Program {n}")
    passes: list[int] = []
    original = match_service.evaluate_all

    def spy(*args: Any, **kwargs: Any) -> Any:
        passes.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(match_service, "evaluate_all", spy)
    before = count(db, OpportunityEvaluation)

    saved = put_match(client)
    assert passes == [1]
    assert (saved["evaluated_opportunities"], saved["unchanged_opportunities"]) == (3, 0)
    assert count(db, OpportunityEvaluation) == before + 3

    # Saving the same Match Profile again appends nothing.
    again = put_match(client)
    assert (again["evaluated_opportunities"], again["unchanged_opportunities"]) == (0, 3)
    assert count(db, OpportunityEvaluation) == before + 3

    # Activities don't score in v1, so changing them doesn't rescore either.
    put_match(client, activities=[])
    assert count(db, OpportunityEvaluation) == before + 3

    changed = put_match(client, skills=["Rust"])
    assert changed["evaluated_opportunities"] == 3
    assert passes == [1, 1, 1, 1]


@pytest.mark.parametrize(
    "changes",
    [
        {"skills": [f"skill {n}" for n in range(51)]},
        {"skills": ["x" * 101]},
        {"skills": [""]},
        {"courses": ["x" * 151]},
        {"interests": [f"interest {n}" for n in range(31)]},
        {"preferred_locations": [f"place {n}" for n in range(21)]},
        {"projects": [{"name": f"p{n}"} for n in range(26)]},
        {"projects": [{"name": "p", "description": "x" * 2001}]},
        {"projects": [{"name": "p", "unknown": 1}]},
        {"remote_preference": "sometimes"},
        {"availability_start": "2041-09-01", "availability_end": "2041-06-01"},
        {"surprise": True},
    ],
)
def test_invalid_match_profile_is_rejected(
    client: TestClient, db: Session, changes: dict[str, Any]
) -> None:
    response = client.put("/api/profile/match", json=MATCH | changes)
    assert response.status_code == 422
    assert count(db, ProfileFact) == 0


def test_match_profile_requires_auth_and_csrf(client: TestClient) -> None:
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.put("/api/profile/match", json=MATCH).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    client.cookies.clear()
    assert client.get("/api/profile/match").status_code == 401


# --- Fit on evaluations ------------------------------------------------------------------------


def test_detail_and_list_expose_the_current_fit(client: TestClient) -> None:
    put_profile(client)
    put_match(client)
    created = create(
        client,
        title="Synthetic Robotics Intern",
        description="Python and SQL for data science on robots.",
        remote_mode="hybrid",
        **COMPLETE,
    )
    evaluation = created["latest_evaluation"]
    breakdown = evaluation["score_breakdown"]
    assert evaluation["scoring_version"] == "v1"
    assert evaluation["fit_score"] == breakdown["score"]
    assert set(breakdown["components"]) == {
        "technical",
        "academic",
        "projects",
        "interests",
        "location_schedule",
        "quality",
    }
    technical = breakdown["components"]["technical"]
    assert technical["matched"] == ["Python", "SQL"] and technical["score"] == 100
    assert breakdown["coverage"] == 100

    [item] = client.get("/api/opportunities").json()["items"]
    assert item["fit_score"] == evaluation["fit_score"]
    assert item["fit_coverage"] == 100
    assert item["fit_components"]["technical"] == {"score": 100, "weight": 35, "missing": False}
    assert "score_breakdown" not in item  # the full breakdown is detail-only


def test_incomplete_profile_shows_low_coverage(client: TestClient) -> None:
    put_profile(client)
    created = create(client)
    breakdown = created["latest_evaluation"]["score_breakdown"]
    assert breakdown["coverage"] == 10  # only opportunity quality
    assert breakdown["components"]["technical"]["missing"] is True
    assert breakdown["components"]["technical"]["missing_input"] == "profile"


def test_pre_scoring_evaluations_get_fit_on_the_next_pass(client: TestClient, db: Session) -> None:
    put_profile(client)
    created = create(client)
    # Simulate a Milestone 3 row: eligibility only.
    db.execute(
        update(OpportunityEvaluation).values(
            fit_score=None, score_breakdown=None, scoring_version=None, fit_input_fingerprint=None
        )
    )
    db.commit()
    assert (
        client.get(f"/api/opportunities/{created['id']}").json()["latest_evaluation"]["fit_score"]
        is None
    )

    saved = put_match(client, skills=[])
    assert saved["evaluated_opportunities"] == 1
    latest = client.get(f"/api/opportunities/{created['id']}").json()["latest_evaluation"]
    assert latest["fit_score"] is not None


# --- Eligibility-first ranking -----------------------------------------------------------------


def test_fit_never_overrides_eligibility(client: TestClient) -> None:
    put_profile(client)
    put_match(client)
    strong = "Python SQL data science robotics robots sensors synthetic rover"
    create(client, title="Eligible weak fit", description="Filing.", **COMPLETE)
    create(client, title="Needs verification strong fit", description=strong)
    create(
        client,
        title="Ineligible strong fit",
        description=strong,
        requirements=[AGE_99],
        **COMPLETE,
    )
    create(client, title="Needs verification weak fit", description="Filing.")

    items = client.get("/api/opportunities", params={"sort": "recommended"}).json()["items"]
    fits = {i["title"]: (i["eligibility_status"], i["fit_score"]) for i in items}
    assert fits["Ineligible strong fit"][0] == "ineligible"
    assert fits["Ineligible strong fit"][1] > fits["Eligible weak fit"][1]
    assert fits["Needs verification strong fit"][1] > fits["Eligible weak fit"][1]
    assert [i["title"] for i in items] == [
        "Eligible weak fit",
        "Needs verification strong fit",
        "Needs verification weak fit",
        "Ineligible strong fit",
    ]


def test_ineligible_fit_100_ranks_below_eligible_fit_1(client: TestClient, db: Session) -> None:
    put_profile(client)
    low = create(client, title="Eligible", **COMPLETE)
    high = create(client, title="Ineligible", requirements=[AGE_99], **COMPLETE)
    # Force the extremes directly on the current evaluations.
    for opportunity_id, score in ((low["id"], 1), (high["id"], 100)):
        db.execute(
            update(OpportunityEvaluation)
            .where(OpportunityEvaluation.opportunity_id == opportunity_id)
            .values(fit_score=score)
        )
    db.commit()
    assert ranked(client) == ["Eligible", "Ineligible"]


def test_without_evaluations_recommended_falls_back_to_newest(client: TestClient) -> None:
    create(client, title="Older")  # no profile: nothing is evaluated
    create(client, title="Newer")
    assert sorted(ranked(client)) == ["Newer", "Older"]
    assert ranked(client) == ranked(client, "newest")


def test_ties_break_by_first_seen_then_id(client: TestClient) -> None:
    put_profile(client)
    ids = {create(client, title=f"Tie {n}", **COMPLETE)["id"]: f"Tie {n}" for n in range(3)}
    # Same bucket, fit, and posted date; the test transaction gives them the same first-seen
    # time, so the ID decides.
    order = ranked(client)
    assert order == [ids[i] for i in sorted(ids)]
    assert order == ranked(client)


def test_fit_orders_inside_a_bucket_and_newest_sort_ignores_fit(client: TestClient) -> None:
    put_profile(client)
    put_match(client, skills=["Python"], courses=[], projects=[], interests=[])
    create(client, title="First created, low fit", description="Filing.", **COMPLETE)
    create(client, title="Second created, high fit", description="Python.", **COMPLETE)
    assert ranked(client) == ["Second created, high fit", "First created, low fit"]
    newest = ranked(client, "newest")
    put_match(client, skills=["Filing"], courses=[], projects=[], interests=[])
    assert ranked(client) == ["First created, low fit", "Second created, high fit"]
    assert ranked(client, "newest") == newest


def test_unknown_sort_is_rejected(client: TestClient) -> None:
    assert client.get("/api/opportunities", params={"sort": "fit"}).status_code == 422


def test_ranking_updates_after_a_match_profile_change(client: TestClient) -> None:
    put_profile(client)
    put_match(client, skills=["Python"], courses=[], projects=[], interests=[])
    create(client, title="Synthetic Python Role", description="Python.", **COMPLETE)
    create(client, title="Synthetic Chemistry Role", description="Chemistry.", **COMPLETE)
    assert ranked(client)[0] == "Synthetic Python Role"
    put_match(client, skills=["Chemistry"], courses=[], projects=[], interests=[])
    assert ranked(client)[0] == "Synthetic Chemistry Role"


def test_fit_reads_only_user_entered_or_verified_facts(client: TestClient, db: Session) -> None:
    put_match(client, skills=["Python"])
    profile = db.scalars(select(Profile)).one()
    db.add_all(
        [
            ProfileFact(  # inferred and unverified: ignored by v1
                profile_id=profile.id,
                category=FactCategory.SKILL,
                fact_key="inferred",
                value={"name": "Synthetic Inferred"},
                source_kind=ProfileSourceKind.RESUME,
                extraction_method=ExtractionMethod.AI_INFERENCE,
                extractor_name="synthetic-extractor",
            ),
            ProfileFact(  # parsed and verified by the owner: used
                profile_id=profile.id,
                category=FactCategory.SKILL,
                fact_key="verified",
                value={"name": "Synthetic Verified"},
                source_kind=ProfileSourceKind.RESUME,
                extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
                verified_by_user=True,
            ),
            ProfileFact(  # malformed value: left out, not coerced
                profile_id=profile.id,
                category=FactCategory.SKILL,
                fact_key="malformed",
                value="Synthetic Malformed",
                source_kind=ProfileSourceKind.MANUAL,
                extraction_method=ExtractionMethod.MANUAL,
            ),
        ]
    )
    db.flush()
    context = evaluation_context(db)
    assert context is not None
    assert set(context.fit.skills) == {"Python", "Synthetic Verified"}
