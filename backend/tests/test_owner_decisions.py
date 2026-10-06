"""Owner decisions on opportunities (ADR-017): durable hide, un-hide, and revert to source.
Synthetic data only."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import IngestionSourceKind
from app.ingestion.adapters import program_registry
from app.ingestion.adapters.community_feed import BUILTIN_IDENTIFIER
from app.ingestion.pipeline import sync_source
from app.models import IngestionSource, Opportunity, OpportunitySourceRecord
from tests.ingestion_fixtures import (
    FEED_URL,
    GREENHOUSE_BOARD,
    GREENHOUSE_URL,
    FakeSource,
    feed,
    feed_job,
    greenhouse_board,
    greenhouse_job,
)
from tests.test_api_workflow import US_CITIZENS, create, put_profile
from tests.test_ingestion import count, sync
from tests.test_program_registry_unit import ENTRY

pytestmark = pytest.mark.postgres

SENTENCE = "Must be a U.S. citizen."
MISSING = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def web() -> FakeSource:
    return FakeSource()


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


def imported(db: Session, source: IngestionSource, web: FakeSource) -> Opportunity:
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content=SENTENCE)))
    sync(db, source, web)
    return db.scalars(select(Opportunity).where(Opportunity.manually_curated_at.is_(None))).one()


def ids(client: TestClient, **params: object) -> set[str]:
    response = client.get("/api/opportunities", params=params)  # type: ignore[arg-type]
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


def test_hide_survives_sync_and_is_not_reimported(
    client: TestClient, db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    opportunity = imported(db, gh_source, web)
    oid = str(opportunity.id)
    assert oid in ids(client)

    response = client.put(f"/api/opportunities/{oid}/dismissal", json={"reason": "not_interested"})
    assert response.status_code == 200, response.text
    assert response.json()["dismissed_reason"] == "not_interested"
    assert oid not in ids(client)
    assert oid not in ids(client, sort="recommended")
    assert oid in ids(client, hidden="only")
    assert oid in ids(client, hidden="include")
    first = response.json()["dismissed_at"]

    # The source changes and syncs again: still one opportunity, still hidden, content updated.
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, title="Renamed Intern")))
    sync(db, gh_source, web)
    db.refresh(opportunity)
    assert count(db, Opportunity) == 1
    assert count(db, OpportunitySourceRecord) == 1
    assert opportunity.dismissed_at is not None
    assert opportunity.title == "Renamed Intern"  # sync still maintains the content
    assert oid not in ids(client)

    # Hiding again keeps the original time; the reason can change.
    again = client.put(f"/api/opportunities/{oid}/dismissal", json={"reason": "other"}).json()
    assert again["dismissed_at"] == first
    assert again["dismissed_reason"] == "other"

    response = client.delete(f"/api/opportunities/{oid}/dismissal")
    assert response.status_code == 200
    assert response.json()["dismissed_at"] is None
    assert oid in ids(client)
    assert oid not in ids(client, hidden="only")


def test_repeat_dismissal_without_a_reason_keeps_the_existing_one(client: TestClient) -> None:
    oid = create(client)["id"]
    client.put(f"/api/opportunities/{oid}/dismissal", json={"reason": "not_eligible"})
    again = client.put(f"/api/opportunities/{oid}/dismissal").json()
    assert again["dismissed_reason"] == "not_eligible"


def test_hide_survives_takeover_fallback_and_reactivation(
    client: TestClient, db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    feed_source = db.scalars(
        select(IngestionSource).where(IngestionSource.identifier == BUILTIN_IDENTIFIER)
    ).one()
    web.json(
        FEED_URL,
        feed(
            feed_job(
                f"greenhouse:{GREENHOUSE_BOARD}:1001",
                url="https://careers.example.com/robotics?gh_jid=1001",
            )
        ),
    )
    sync(db, feed_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    oid = str(opportunity.id)
    client.put(f"/api/opportunities/{oid}/dismissal", json={"reason": "other"})

    def still_hidden() -> None:
        db.refresh(opportunity)
        assert opportunity.dismissed_at is not None
        assert opportunity.dismissed_reason == "other"
        assert count(db, Opportunity) == 1
        assert oid not in ids(client)

    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content=SENTENCE)))
    sync(db, gh_source, web)  # takeover by the ATS record
    assert opportunity.description == SENTENCE
    still_hidden()
    web.json(GREENHOUSE_URL, greenhouse_board())
    sync(db, gh_source, web)  # the ATS record closes: fallback to the feed
    still_hidden()
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content=SENTENCE)))
    sync(db, gh_source, web)  # reactivation
    still_hidden()


def edit_body(client: TestClient, oid: str, **changes: Any) -> dict[str, Any]:
    body = client.get(f"/api/opportunities/{oid}").json()
    edit: dict[str, Any] = {
        "title": body["title"],
        "organization": body["organization"],
        "opportunity_type": body["opportunity_type"],
        "description": body["description"],
        "application_deadline": body["application_deadline"],
        "requirements": [],
    }
    response = client.put(f"/api/opportunities/{oid}", json=edit | changes)
    assert response.status_code == 200, response.text
    return response.json()


def test_revert_keeps_tracking_and_hidden_state(
    client: TestClient, db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    oid = str(imported(db, gh_source, web).id)
    client.put(f"/api/opportunities/{oid}/application", json={"status": "saved"})
    client.put(f"/api/opportunities/{oid}/dismissal", json={"reason": "other"})
    edit_body(client, oid, title="Owner Edit")

    reverted = client.post(f"/api/opportunities/{oid}/revert-to-source").json()

    assert reverted["title"] != "Owner Edit"
    assert reverted["application"]["status"] == "saved"
    assert reverted["dismissed_at"] is not None and reverted["dismissed_reason"] == "other"


def test_revert_of_a_feed_owned_opportunity_keeps_its_description(
    client: TestClient, db: Session, web: FakeSource
) -> None:
    feed_source = db.scalars(
        select(IngestionSource).where(IngestionSource.identifier == BUILTIN_IDENTIFIER)
    ).one()
    web.json(FEED_URL, feed(feed_job()))
    sync(db, feed_source, web)
    oid = str(db.scalars(select(Opportunity)).one().id)
    edit_body(client, oid, title="Owner Edit", description="Known text.")

    reverted = client.post(f"/api/opportunities/{oid}/revert-to-source").json()

    assert reverted["title"] == "Synthetic Engineering Intern"
    assert reverted["description"] == "Known text."  # a feed owner never erases it (ADR-013 §4)


@pytest.mark.registry
def test_revert_of_a_registry_program_restores_its_dates(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "r.json"
    path.write_text(
        json.dumps({"schema_version": 1, "programs": [copy.deepcopy(ENTRY)]}), encoding="utf-8"
    )
    monkeypatch.setattr(program_registry, "REGISTRY_PATH", path)
    source = db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.CURATED_REGISTRY)
    ).one()
    sync_source(db, source)
    oid = str(db.scalars(select(Opportunity)).one().id)
    edit_body(client, oid, title="Owner Edit", application_deadline="2041-02-01")

    reverted = client.post(f"/api/opportunities/{oid}/revert-to-source").json()

    assert reverted["title"] == ENTRY["title"]
    assert reverted["application_deadline"] == ENTRY["verified"]["deadline"]
    assert reverted["start_date"] == ENTRY["verified"]["start_date"]
    assert reverted["verify_by"] == ENTRY["verify_by"]
    assert reverted["manually_curated_at"] is None


def test_revert_of_an_unnormalizable_stored_item_is_refused_unchanged(
    client: TestClient, db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    opportunity = imported(db, gh_source, web)
    oid = str(opportunity.id)
    edit_body(client, oid, title="Owner Edit")
    record = db.scalars(select(OpportunitySourceRecord)).one()
    record.raw_payload = {"not": "a greenhouse job"}
    db.commit()

    response = client.post(f"/api/opportunities/{oid}/revert-to-source")

    assert response.status_code == 409
    after = client.get(f"/api/opportunities/{oid}").json()
    assert after["title"] == "Owner Edit" and after["manually_curated_at"] is not None


def test_dismiss_without_body_bad_reason_and_missing(client: TestClient) -> None:
    oid = create(client)["id"]
    assert client.put(f"/api/opportunities/{oid}/dismissal").status_code == 200
    bad = client.put(f"/api/opportunities/{oid}/dismissal", json={"reason": "bogus"})
    assert bad.status_code == 422
    assert client.put(f"/api/opportunities/{MISSING}/dismissal").status_code == 404


def test_revert_restores_source_content_and_re_evaluates(
    client: TestClient, db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    put_profile(client)
    opportunity = imported(db, gh_source, web)
    oid = str(opportunity.id)
    source_title = opportunity.title
    source_description = opportunity.description
    body = client.get(f"/api/opportunities/{oid}").json()
    edit = {
        "title": "Owner Edit",
        "organization": body["organization"],
        "opportunity_type": body["opportunity_type"],
        "description": "Owner text.",
        "application_deadline": "2041-02-01",
        "requirements": [US_CITIZENS],
    }
    edited = client.put(f"/api/opportunities/{oid}", json=edit).json()
    assert edited["manually_curated_at"] and edited["title"] == "Owner Edit"
    assert len(edited["requirements"]) == 1
    evaluation_before = edited["latest_evaluation"]["id"]

    response = client.post(f"/api/opportunities/{oid}/revert-to-source")
    assert response.status_code == 200, response.text
    reverted = response.json()
    assert reverted["manually_curated_at"] is None
    assert reverted["title"] == source_title
    assert reverted["description"] == source_description
    assert reverted["application_deadline"] is None
    assert reverted["requirements"] == []
    assert reverted["requirements_assessment_status"] == "unassessed"
    assert reverted["pending_requirement_count"] == 1  # the source text proposes a candidate
    assert reverted["latest_evaluation"]["id"] != evaluation_before  # re-evaluated
    assert len(reverted["sources"]) == 1  # provenance kept

    # Syncs own the content again.
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, title="Renamed Intern")))
    sync(db, gh_source, web)
    assert client.get(f"/api/opportunities/{oid}").json()["title"] == "Renamed Intern"


def test_revert_refused_without_edits_manual_or_active_source(
    client: TestClient, db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    manual = create(client)["id"]
    response = client.post(f"/api/opportunities/{manual}/revert-to-source")
    assert response.status_code == 409
    assert "no source" in response.json()["detail"]

    opportunity = imported(db, gh_source, web)
    oid = str(opportunity.id)
    assert client.post(f"/api/opportunities/{oid}/revert-to-source").status_code == 409  # no edits

    body = client.get(f"/api/opportunities/{oid}").json()
    edit: dict[str, Any] = {
        "organization": body["organization"],
        "opportunity_type": body["opportunity_type"],
        "title": "Owner Edit",
        "requirements": [],
    }
    client.put(f"/api/opportunities/{oid}", json=edit)
    web.json(GREENHOUSE_URL, greenhouse_board())  # posting closes: no active source
    sync(db, gh_source, web)
    response = client.post(f"/api/opportunities/{oid}/revert-to-source")
    assert response.status_code == 409
    assert client.get(f"/api/opportunities/{oid}").json()["title"] == "Owner Edit"


@pytest.mark.parametrize("csrf", [None, "wrong-token"])
def test_new_endpoints_require_csrf_and_auth(
    client: TestClient, anon_client: TestClient, csrf: str | None
) -> None:
    oid = create(client)["id"]
    headers = {} if csrf is None else {"X-CSRF-Token": csrf}
    del client.headers["X-CSRF-Token"]
    for method, path in (
        ("PUT", f"/api/opportunities/{oid}/dismissal"),
        ("DELETE", f"/api/opportunities/{oid}/dismissal"),
        ("POST", f"/api/opportunities/{oid}/revert-to-source"),
    ):
        assert client.request(method, path, headers=headers).status_code == 403, path
    anon_client.cookies.clear()
    assert anon_client.put(f"/api/opportunities/{oid}/dismissal").status_code == 401
