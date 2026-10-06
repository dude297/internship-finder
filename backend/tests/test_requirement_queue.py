"""Global requirement review queue (ADR-024): filters, paging, duplicate flag, summary, batch
reject, auth/CSRF, and the constant statement count. Synthetic data only."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from app.enums import (
    FactReviewState,
    IngestionSourceKind,
    OpportunitySourceType,
    RequirementType,
)
from app.models import (
    IngestionSource,
    Opportunity,
    OpportunityRequirement,
    OpportunityRequirementCandidate,
    OpportunitySourceRecord,
)
from tests.test_api_requirement_review import add_candidate, review_url
from tests.test_api_workflow import AGE_16, create, put_profile

pytestmark = pytest.mark.postgres

QUEUE = "/api/requirement-review/queue"
BATCH = "/api/requirement-review/reject-batch"
EDU = {"levels": ["undergraduate"], "accepts_incoming": False}


def queue(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get(QUEUE, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def ids(page: dict[str, Any]) -> set[str]:
    return {item["candidate"]["id"] for item in page["items"]}


def candidate_state(db: Session, candidate_id: Any) -> FactReviewState:
    db.expire_all()
    row = db.get(OpportunityRequirementCandidate, candidate_id)
    assert row is not None
    return row.review_state


# --- Auth and CSRF -------------------------------------------------------------------------


def test_queue_requires_auth(anon_client: TestClient) -> None:
    assert anon_client.get(QUEUE).status_code == 401
    assert anon_client.post(BATCH, json={"candidate_ids": []}).status_code == 401


def test_batch_requires_csrf(client: TestClient, db: Session) -> None:
    created = create(client)
    cand = add_candidate(db, created["id"])
    client.headers.pop("X-CSRF-Token")

    assert client.post(BATCH, json={"candidate_ids": [str(cand.id)]}).status_code == 403
    assert candidate_state(db, cand.id) is FactReviewState.PENDING


# --- Queue content, filters, paging ---------------------------------------------------------


def test_queue_item_has_evidence_opportunity_and_existing_requirements(
    client: TestClient, db: Session
) -> None:
    created = create(client, title="Queue Item Program", requirements=[AGE_16])
    cand = add_candidate(db, created["id"], requirement_type=RequirementType.EDUCATION, value=EDU)

    page = queue(client)

    assert page["total"] == 1
    item = page["items"][0]
    assert item["candidate"]["id"] == str(cand.id)
    assert item["candidate"]["source_text"] == cand.source_text
    assert item["opportunity"]["title"] == "Queue Item Program"
    assert item["opportunity"]["freshness"] == "manual"
    assert [r["requirement_type"] for r in item["existing_requirements"]] == ["minimum_age"]
    assert item["duplicate_of"] is None


def test_hidden_accepted_and_rejected_are_not_queued(client: TestClient, db: Session) -> None:
    visible = create(client, title="Visible")
    hidden = create(client, title="Hidden")
    add_candidate(db, visible["id"], value={"years": 16})
    add_candidate(db, visible["id"], value={"years": 17}, review_state=FactReviewState.ACCEPTED)
    add_candidate(db, visible["id"], value={"years": 18}, review_state=FactReviewState.REJECTED)
    add_candidate(db, hidden["id"])
    assert client.put(f"/api/opportunities/{hidden['id']}/dismissal").status_code == 200

    page = queue(client)

    assert page["total"] == 1
    assert page["items"][0]["candidate"]["value"] == {"years": 16}
    assert page["summary"]["pending_total"] == 1


def test_filters_map_to_stored_columns(client: TestClient, db: Session) -> None:
    acme = create(client, title="A", organization="Acme Labs")
    other = create(client, title="B", organization="Other Org")
    age = add_candidate(db, acme["id"])
    edu = add_candidate(db, acme["id"], requirement_type=RequirementType.EDUCATION, value=EDU)
    old = add_candidate(db, other["id"], value={"years": 18})
    db.execute(
        update(OpportunityRequirementCandidate)
        .where(OpportunityRequirementCandidate.id == old.id)
        .values(extractor_version="2", created_at=datetime.now(UTC) - timedelta(days=30))
    )
    db.commit()

    assert ids(queue(client, requirement_type="education")) == {str(edu.id)}
    assert ids(queue(client, organization="acme")) == {str(age.id), str(edu.id)}
    assert ids(queue(client, extractor_version="2")) == {str(old.id)}
    assert ids(queue(client, extractor_name="requirements-rules", extractor_version="1")) == {
        str(age.id),
        str(edu.id),
    }
    assert ids(queue(client, opportunity_id=other["id"])) == {str(old.id)}
    since = (date.today() - timedelta(days=2)).isoformat()
    assert ids(queue(client, created_since=since)) == {str(age.id), str(edu.id)}
    assert queue(client, extractor_name="nope")["total"] == 0
    # `%` and `_` in the organization filter are literal, not wildcards.
    assert queue(client, organization="%")["total"] == 0


def test_bad_filter_values_are_422(client: TestClient) -> None:
    assert client.get(QUEUE, params={"requirement_type": "bogus"}).status_code == 422
    assert client.get(QUEUE, params={"limit": 101}).status_code == 422
    assert client.get(QUEUE, params={"limit": 0}).status_code == 422
    assert client.get(QUEUE, params={"offset": -1}).status_code == 422
    assert client.get(QUEUE, params={"created_since": "1999-01-01"}).status_code == 422


def test_source_kind_and_posting_changed_filters(client: TestClient, db: Session) -> None:
    from_board = create(client, title="Board")
    manual = create(client, title="Manual")
    changed = create(client, title="Changed")
    source = IngestionSource(
        kind=IngestionSourceKind.GREENHOUSE, identifier="queue-test", display_name="Queue Test"
    )
    db.add(source)
    db.flush()
    db.add(
        OpportunitySourceRecord(
            opportunity_id=from_board["id"],
            source_name="queue-board",
            source_type=OpportunitySourceType.ATS,
            fetched_at=datetime.now(UTC),
            ingestion_source_id=source.id,
        )
    )
    db.execute(
        update(Opportunity)
        .where(Opportunity.id == changed["id"])
        .values(requirements_stale_since=datetime.now(UTC))
    )
    c_board = add_candidate(db, from_board["id"])
    add_candidate(db, manual["id"])
    c_changed = add_candidate(db, changed["id"])

    assert ids(queue(client, source_kind="greenhouse")) == {str(c_board.id)}
    assert ids(queue(client, source_kind="lever")) == set()
    assert ids(queue(client, posting_changed="true")) == {str(c_changed.id)}
    board_item = queue(client, source_kind="greenhouse")["items"][0]["opportunity"]
    assert "queue-board" in board_item["source_names"]
    assert board_item["source_kinds"] == ["greenhouse"]


def test_pagination_is_bounded_and_ordered(client: TestClient, db: Session) -> None:
    created = create(client)
    for years in range(14, 21):
        add_candidate(db, created["id"], value={"years": years})

    first = queue(client, limit=3, offset=0)
    second = queue(client, limit=3, offset=3)
    last = queue(client, limit=3, offset=6)

    assert [len(p["items"]) for p in (first, second, last)] == [3, 3, 1]
    assert first["total"] == second["total"] == last["total"] == 7
    assert not ids(first) & ids(second)
    assert len(ids(first) | ids(second) | ids(last)) == 7
    assert queue(client, limit=3, offset=50)["items"] == []


# --- Duplicate flag -------------------------------------------------------------------------


def test_duplicate_flag_matches_semantic_key_not_text(client: TestClient, db: Session) -> None:
    created = create(
        client,
        requirements=[
            AGE_16,
            {
                "requirement_type": "education",
                "value": {"levels": ["undergraduate"], "accepts_incoming": False},
                "applies_at": "program_start",
                "reference_date": None,
            },
        ],
    )
    same = add_candidate(db, created["id"], source_text="Must be sixteen or older.")
    different_value = add_candidate(db, created["id"], value={"years": 18})
    # Same meaning as the education requirement,.
    same_edu = add_candidate(
        db,
        created["id"],
        requirement_type=RequirementType.EDUCATION,
        value={"levels": ["undergraduate"], "accepts_incoming": False},
    )

    items = {i["candidate"]["id"]: i for i in queue(client)["items"]}

    assert items[str(same.id)]["duplicate_of"] is not None
    assert items[str(same_edu.id)]["duplicate_of"] is not None
    assert items[str(different_value.id)]["duplicate_of"] is None


def test_accepting_a_duplicate_links_without_creating_a_second_requirement(
    client: TestClient, db: Session
) -> None:
    created = create(client, requirements=[AGE_16])
    cand = add_candidate(db, created["id"])
    assert queue(client)["items"][0]["duplicate_of"] is not None

    # The existing single-opportunity endpoint is the only accept path (no queue-side write).
    response = client.post(review_url(created["id"]), json={"accept": [{"id": str(cand.id)}]})

    assert response.status_code == 200, response.text
    db.expire_all()
    requirements = db.scalars(
        select(OpportunityRequirement).where(OpportunityRequirement.opportunity_id == created["id"])
    ).all()
    assert len(requirements) == 1
    assert candidate_state(db, cand.id) is FactReviewState.ACCEPTED
    assert queue(client)["total"] == 0


# --- Summary --------------------------------------------------------------------------------


def test_summary_counts_pending_by_type_and_reviewed_today(client: TestClient, db: Session) -> None:
    created = create(client)
    old = datetime.now(UTC) - timedelta(days=5)
    add_candidate(db, created["id"], value={"years": 14})
    add_candidate(db, created["id"], value={"years": 15})
    add_candidate(db, created["id"], requirement_type=RequirementType.EDUCATION, value=EDU)
    add_candidate(db, created["id"], value={"years": 20}, review_state=FactReviewState.ACCEPTED)
    stale_reviewed = add_candidate(
        db, created["id"], value={"years": 21}, review_state=FactReviewState.REJECTED
    )
    db.execute(
        update(OpportunityRequirementCandidate)
        .where(OpportunityRequirementCandidate.id == stale_reviewed.id)
        .values(updated_at=old)
    )
    db.commit()

    summary = queue(client)["summary"]

    assert summary["pending_total"] == 3
    assert {c["requirement_type"]: c["count"] for c in summary["by_type"]} == {
        "minimum_age": 2,
        "education": 1,
    }
    assert summary["accepted_today"] == 1
    assert summary["rejected_today"] == 0  # reviewed five days ago
    assert summary["extractor_versions"] == ["1"]
    # Filters narrow the page, never the progress summary.
    narrowed = queue(client, requirement_type="education")
    assert narrowed["total"] == 1
    assert narrowed["summary"]["pending_total"] == 3


# --- Statement count ------------------------------------------------------------------------


def statements(client: TestClient, db: Session, **params: Any) -> int:
    seen: list[str] = []

    def count(*args: Any) -> None:
        seen.append(args[2])

    queue(client, **params)  # warm the session
    event.listen(db.get_bind(), "before_cursor_execute", count)
    try:
        queue(client, **params)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count)
    return len(seen)


def test_statement_count_does_not_grow_with_the_queue(client: TestClient, db: Session) -> None:
    first = create(client, title="First", requirements=[AGE_16])
    add_candidate(db, first["id"], value={"years": 17})
    before = statements(client, db, limit=100)

    for n in range(12):
        created = create(client, title=f"Bulk {n}", requirements=[AGE_16])
        add_candidate(db, created["id"], value={"years": 14})
        add_candidate(db, created["id"], value={"years": 15})

    assert queue(client, limit=100)["total"] == 25
    assert statements(client, db, limit=100) == before


# --- Batch reject ---------------------------------------------------------------------------


def test_batch_reject_across_opportunities_goes_through_the_review_service(
    client: TestClient, db: Session
) -> None:
    put_profile(client)
    one = create(client, title="One")
    two = create(client, title="Two")
    a = add_candidate(db, one["id"], value={"years": 14})
    b = add_candidate(db, one["id"], value={"years": 15})
    c = add_candidate(db, two["id"], value={"years": 16})
    keep = add_candidate(db, two["id"], value={"years": 17})

    response = client.post(BATCH, json={"candidate_ids": [str(a.id), str(b.id), str(c.id)]})

    assert response.status_code == 200, response.text
    assert response.json()["rejected"] == 3
    assert response.json()["opportunities"] == 2
    assert [candidate_state(db, x.id) for x in (a, b, c, keep)] == [
        FactReviewState.REJECTED,
        FactReviewState.REJECTED,
        FactReviewState.REJECTED,
        FactReviewState.PENDING,
    ]
    # Rejecting accepts and creates nothing.
    assert db.scalars(select(OpportunityRequirement)).all() == []
    assert queue(client)["total"] == 1


def test_batch_is_all_or_nothing(client: TestClient, db: Session) -> None:
    created = create(client)
    pending = add_candidate(db, created["id"], value={"years": 14})
    accepted = add_candidate(db, created["id"], value={"years": 15})
    client.post(review_url(created["id"]), json={"accept": [{"id": str(accepted.id)}]})
    unknown = "00000000-0000-0000-0000-000000000000"

    already = client.post(BATCH, json={"candidate_ids": [str(pending.id), str(accepted.id)]})
    missing = client.post(BATCH, json={"candidate_ids": [str(pending.id), unknown]})

    assert already.status_code == 422
    assert missing.status_code == 404
    assert candidate_state(db, pending.id) is FactReviewState.PENDING
    # The accepted suggestion and its requirement were never touched.
    assert candidate_state(db, accepted.id) is FactReviewState.ACCEPTED
    assert len(db.scalars(select(OpportunityRequirement)).all()) == 1


def test_batch_validation_and_bounds(client: TestClient, db: Session) -> None:
    created = create(client)
    cand = add_candidate(db, created["id"])
    same = str(cand.id)

    assert client.post(BATCH, json={"candidate_ids": []}).status_code == 422
    assert client.post(BATCH, json={"candidate_ids": ["not-a-uuid"]}).status_code == 422
    assert client.post(BATCH, json={"candidate_ids": [same, same]}).status_code == 422
    assert client.post(BATCH, json={"candidate_ids": [same], "accept": []}).status_code == 422
    too_many = [f"00000000-0000-0000-0000-{n:012d}" for n in range(101)]
    assert client.post(BATCH, json={"candidate_ids": too_many}).status_code == 422
    assert candidate_state(db, cand.id) is FactReviewState.PENDING


def test_batch_reject_of_more_than_one_review_chunk_in_one_opportunity(
    client: TestClient, db: Session
) -> None:
    created = create(client)
    cands = [add_candidate(db, created["id"], value={"years": 10 + n}) for n in range(60)]

    response = client.post(BATCH, json={"candidate_ids": [str(c.id) for c in cands]})

    assert response.status_code == 200, response.text
    assert queue(client)["total"] == 0
