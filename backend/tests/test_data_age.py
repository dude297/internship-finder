"""Data-age banner endpoint and the posted_within filter. Synthetic data only. Times are relative
to now with half-hour/half-day margins around each boundary, so no clock freezing is needed."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.enums import IngestionSourceKind
from app.models import IngestionSource, Opportunity
from tests.test_api_workflow import create

pytestmark = pytest.mark.postgres


def hours_ago(h: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=h)


def freshness(client: TestClient) -> dict[str, object]:
    response = client.get("/api/status/freshness")
    assert response.status_code == 200, response.text
    return response.json()


def test_freshness_thresholds(client: TestClient, db: Session) -> None:
    db.execute(update(IngestionSource).values(enabled=False))
    db.commit()
    assert freshness(client)["reason"] == "no_sources"
    source = IngestionSource(
        kind=IngestionSourceKind.GREENHOUSE, identifier="age-test", display_name="Age Test"
    )
    db.add(source)
    db.commit()
    body = freshness(client)
    assert body["stale"] is True and body["reason"] == "never_synced"
    source.last_success_at = hours_ago(35.5)
    db.commit()
    assert freshness(client)["stale"] is False
    source.last_success_at = hours_ago(36.5)
    db.commit()
    body = freshness(client)
    assert body["stale"] is True and body["reason"] == "stale"
    # The newest enabled source wins; a disabled fresh one does not count.
    other = IngestionSource(
        kind=IngestionSourceKind.ASHBY,
        identifier="age-test-2",
        display_name="Age Test 2",
        enabled=False,
        last_success_at=hours_ago(1),
    )
    db.add(other)
    db.commit()
    assert freshness(client)["stale"] is True
    other.enabled = True
    db.commit()
    assert freshness(client)["stale"] is False


def test_posted_within_boundaries(client: TestClient, db: Session) -> None:
    ages = {"d6": 6.5, "d8": 7.5, "d29": 29.5, "d31": 30.5, "d89": 89.5, "d91": 90.5}
    for name, days in ages.items():
        opportunity_id = create(client, title=f"Posted {name}")["id"]
        db.execute(
            update(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .values(posted_at=datetime.now(UTC) - timedelta(days=days))
        )
    create(client, title="Posted none")
    db.commit()

    def got(**params: object) -> set[str]:
        r = client.get("/api/opportunities", params={"limit": 50, **params})  # type: ignore[arg-type]
        assert r.status_code == 200, r.text
        return {i["title"].removeprefix("Posted ") for i in r.json()["items"]}

    assert got() == {*ages, "none"}  # no filter: everything, NULL posted_at included
    assert got(posted_within=7) == {"d6"}
    assert got(posted_within="30") == {"d6", "d8", "d29"}
    assert got(posted_within=90) == {"d6", "d8", "d29", "d31", "d89"}
    assert client.get("/api/opportunities", params={"posted_within": 14}).status_code == 422
