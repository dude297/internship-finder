"""SmartRecruiters across the real pipeline (ADR-014 §2-§3, ADR-013): feed-first and ATS-first
orderings, discovery, takeover/fallback, detail failures, identity conflicts, and steady-state
request counts. Synthetic data only; one in-memory transport serves the feed and the API."""

from collections import Counter
from datetime import date
from functools import partial
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.enums import (
    EducationLevel,
    EligibilityStatus,
    FactReviewState,
    IngestionRunStatus,
    IngestionSourceKind,
    RequirementsAssessmentStatus,
    SourceScope,
)
from app.ingestion.adapters import smartrecruiters
from app.ingestion.adapters.community_feed import BUILTIN_IDENTIFIER
from app.ingestion.http import fetch_json
from app.ingestion.pipeline import sync_enabled_sources, sync_source
from app.models import (
    IngestionRun,
    IngestionSource,
    Opportunity,
    OpportunityRequirement,
    OpportunitySourceRecord,
    Profile,
)
from app.repositories import latest_evaluation
from tests.ingestion_fixtures import FEED_URL, feed, feed_job
from tests.test_smartrecruiters_adapter import detail_for, list_item, pid

pytestmark = pytest.mark.postgres

SR_API = "https://api.smartrecruiters.com/v1/companies"
COMPANY = "examplerobotics"
ID1 = pid(1)
FEED_ID = f"smartrecruiters:ExampleRobotics:{ID1}"
SENTENCE = "Applicants must be at least 18 years old."


def _no_sleep_fetch() -> Any:
    return partial(fetch_json, sleep=lambda _s: None)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smartrecruiters, "fetch_json", _no_sleep_fetch())


class World:
    """The feed and the Posting API for any number of companies, counting hits per URL."""

    def __init__(self) -> None:
        self.feed_jobs: list[dict[str, Any]] = []
        self.postings: dict[str, list[dict[str, Any]]] = {}
        self.detail_status: dict[tuple[str, str], int] = {}
        self.hits: Counter[str] = Counter()
        self.transport = httpx2.MockTransport(self._handle)

    def detail_hits(self) -> int:
        return sum(n for url, n in self.hits.items() if url.startswith(SR_API) and "?" not in url)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        self.hits[url] += 1
        if url == FEED_URL:
            return httpx2.Response(200, json=feed(*self.feed_jobs))
        assert url.startswith(SR_API + "/"), url
        company, _, rest = url[len(SR_API) + 1 :].partition("/postings")
        items = self.postings[company]
        if rest.startswith("?"):
            offset = int(rest.split("offset=")[1].split("&")[0])
            return httpx2.Response(
                200,
                json={
                    "offset": offset,
                    "limit": 100,
                    "totalFound": len(items),
                    "content": items[offset : offset + 100],
                },
            )
        posting_id = rest.strip("/")
        item = next((i for i in items if i["id"] == posting_id), None)
        status = self.detail_status.get((company, posting_id), 200)
        if item is None or status != 200:
            return httpx2.Response(status if item else 404)
        sections = {
            "jobDescription": {"title": "Job Description", "text": "<p>Build robots.</p>"},
            "qualifications": {"title": "Qualifications", "text": f"<p>{SENTENCE}</p>"},
        }
        link = f"https://jobs.smartrecruiters.com/{item['company']['identifier']}/{posting_id}"
        detail = detail_for(item, jobAd={"sections": sections}, postingUrl=link)
        return httpx2.Response(200, json=detail)


def sr_item(n: int = 1, company: str = "ExampleRobotics", **changes: Any) -> dict[str, Any]:
    return list_item(n, name="Synthetic Engineering Intern", **changes) | {
        "company": {"identifier": company, "name": company}
    }


def feed_sr(n: int = 1) -> dict[str, Any]:
    return feed_job(
        f"smartrecruiters:ExampleRobotics:{pid(n)}",
        url=f"https://jobs.smartrecruiters.com/ExampleRobotics/{pid(n)}",
        title="Synthetic Engineering Intern",
    )


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def feed_source(db: Session) -> IngestionSource:
    return db.scalars(
        select(IngestionSource).where(IngestionSource.identifier == BUILTIN_IDENTIFIER)
    ).one()


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


def make_sr(db: Session, company: str = COMPANY) -> IngestionSource:
    source = IngestionSource(
        kind=IngestionSourceKind.SMARTRECRUITERS,
        identifier=company,
        display_name=company,
        scope=SourceScope.INTERNSHIPS_ONLY,
    )
    db.add(source)
    db.commit()
    return source


def sync(db: Session, source: IngestionSource, world: World) -> IngestionRun:
    return sync_source(db, source, transport=world.transport)


def opps(db: Session) -> list[Opportunity]:
    return list(db.scalars(select(Opportunity)).all())


def record(db: Session, source: IngestionSource) -> OpportunitySourceRecord:
    return db.scalars(
        select(OpportunitySourceRecord).where(
            OpportunitySourceRecord.ingestion_source_id == source.id
        )
    ).one()


def eligibility(db: Session, profile: Profile, opportunity: Opportunity) -> EligibilityStatus:
    evaluation = latest_evaluation(db, profile.id, opportunity.id)
    assert evaluation is not None
    return evaluation.eligibility_status


def test_full_lifecycle_feed_first(
    db: Session,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    feed_source: IngestionSource,
    world: World,
    profile: Profile,
) -> None:
    # 1. Feed-only.
    world.feed_jobs = [feed_sr()]
    sync(db, feed_source, world)
    opportunity = db.scalars(select(Opportunity)).one()
    assert opportunity.description is None and opportunity.requirement_candidates == []
    before = eligibility(db, profile, opportunity)

    # 2. Discovery is derived from the database: no fetch at all.
    def boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("discovery must not touch the network")

    hits = sum(world.hits.values())
    with monkeypatch.context() as patch:
        patch.setattr("app.ingestion.http.fetch_json", boom)
        patch.setattr(smartrecruiters, "fetch_json", boom)
        body = client.get("/api/sources/discovery").json()
        [suggestion] = body["suggestions"]
        assert (suggestion["kind"], suggestion["identifier"]) == ("smartrecruiters", COMPANY)
        [provider] = [p for p in body["providers"] if p["provider"] == "smartrecruiters"]
        assert provider["supported"] is True and provider["enrichable"] == 1

        # 3. Add through discovery: internships_only, and no sync.
        added = client.post(
            "/api/sources/discovery/add",
            json={"sources": [{"kind": "smartrecruiters", "identifier": COMPANY}]},
        )
        assert added.status_code == 201, added.text
        assert added.json()["created"][0]["scope"] == "internships_only"
    assert sum(world.hits.values()) == hits
    sr = db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.SMARTRECRUITERS)
    ).one()
    assert db.scalars(select(IngestionRun).where(IngestionRun.source_id == sr.id)).all() == []

    # 4. SR sync: same opportunity, ATS owns the text, suggestions only.
    world.postings[COMPANY] = [sr_item()]
    run = sync(db, sr, world)
    assert run.status is IngestionRunStatus.SUCCESS
    assert (run.fetched_count, run.deduplicated_count, run.created_count) == (1, 1, 0)
    assert len(opps(db)) == 1
    db.refresh(opportunity)
    assert "Build robots." in (opportunity.description or "")
    description = opportunity.description
    [candidate] = opportunity.requirement_candidates
    assert candidate.review_state is FactReviewState.PENDING
    assert db.scalars(select(OpportunityRequirement)).all() == []
    assert opportunity.requirements_assessment_status is RequirementsAssessmentStatus.UNASSESSED
    assert eligibility(db, profile, opportunity) == before
    sr_record, feed_record = record(db, sr), record(db, feed_source)
    assert sr_record.is_active and feed_record.is_active

    # 5. SR posting removed while the feed still has it: the feed falls back, text kept.
    world.postings[COMPANY] = []
    run = sync(db, sr, world)
    assert run.status is IngestionRunStatus.SUCCESS and run.closed_count == 1
    db.refresh(opportunity)
    db.refresh(sr_record)
    db.refresh(feed_record)
    assert not sr_record.is_active and feed_record.is_active
    assert opportunity.description == description
    assert len(opps(db)) == 1

    # 6. It returns: ATS owns again, same opportunity.
    world.postings[COMPANY] = [sr_item()]
    run = sync(db, sr, world)
    assert run.reactivated_count == 1
    db.refresh(sr_record)
    assert sr_record.is_active and len(opps(db)) == 1


def test_sr_first_then_feed_and_enabled_order(
    db: Session, feed_source: IngestionSource, world: World
) -> None:
    sr = make_sr(db)
    world.postings[COMPANY] = [sr_item()]
    assert sync(db, sr, world).created_count == 1
    world.feed_jobs = [feed_sr()]
    assert sync(db, feed_source, world).deduplicated_count == 1
    [opportunity] = opps(db)
    assert "Build robots." in (opportunity.description or "")  # the feed never overwrote it

    # sync_enabled_sources runs SR before the feed, from scratch.
    db.execute(delete(Opportunity))
    db.commit()
    runs = sync_enabled_sources(db, transport=world.transport)
    assert runs[-1].source.kind is IngestionSourceKind.COMMUNITY_FEED
    [opportunity] = opps(db)
    assert "Build robots." in (opportunity.description or "")


def test_detail_failure_is_partial_and_changes_nothing(
    db: Session, feed_source: IngestionSource, world: World
) -> None:
    sr = make_sr(db)
    world.postings[COMPANY] = [sr_item()]
    world.feed_jobs = [feed_sr()]
    sync(db, feed_source, world)
    sync(db, sr, world)
    [opportunity] = opps(db)
    description = opportunity.description
    sr_record = record(db, sr)
    stored = (sr_record.raw_payload, sr_record.content_hash)

    # The listing changed (the stored detail can't be reused) and the detail now fails.
    world.postings[COMPANY] = [sr_item(releasedDate="2040-10-01T00:00:00.000Z")]
    for status in (500, 404):
        world.detail_status[(COMPANY, ID1)] = status
        run = sync(db, sr, world)
        assert run.status is IngestionRunStatus.PARTIAL
        assert run.closed_count == 0
        db.refresh(opportunity)
        db.refresh(sr_record)
        assert sr_record.is_active
        assert (sr_record.raw_payload, sr_record.content_hash) == stored
        assert opportunity.description == description


def test_feed_link_naming_another_company_or_id_never_merges(
    db: Session, feed_source: IngestionSource, world: World
) -> None:
    sr = make_sr(db)
    world.postings[COMPANY] = [sr_item()]
    world.feed_jobs = [
        feed_job(
            FEED_ID,
            title="Synthetic Engineering Intern",
            url=f"https://jobs.smartrecruiters.com/OtherCompany/{ID1}",
        ),
        feed_job(
            f"smartrecruiters:ExampleRobotics:{ID1}9",
            title="Synthetic Engineering Intern",
            url=f"https://jobs.smartrecruiters.com/ExampleRobotics/{pid(3)}",
        ),
    ]
    sync(db, feed_source, world)
    assert len(opps(db)) == 2
    sync(db, sr, world)
    assert len(opps(db)) == 3  # the SR posting stands alone
    feed_opportunities = {
        r.opportunity_id
        for r in db.scalars(select(OpportunitySourceRecord)).all()
        if r.ingestion_source_id == feed_source.id
    }
    assert record(db, sr).opportunity_id not in feed_opportunities


def test_same_posting_id_in_two_companies_stays_distinct(db: Session, world: World) -> None:
    for company in ("examplerobotics", "examplelabs"):
        make_sr(db, company)
        world.postings[company] = [sr_item(1, company=company)]
    runs = sync_enabled_sources(db, transport=world.transport)
    assert all(r.status is IngestionRunStatus.SUCCESS for r in runs)
    assert len(opps(db)) == 2


def test_steady_state_makes_no_detail_requests(db: Session, world: World) -> None:
    sr = make_sr(db)
    world.postings[COMPANY] = [sr_item(n) for n in range(1, 6)]
    run = sync(db, sr, world)
    assert run.created_count == 5 and world.detail_hits() == 5
    world.hits.clear()
    run = sync(db, sr, world)
    assert run.unchanged_count == 5 and run.updated_count == 0 and run.created_count == 0
    assert world.detail_hits() == 0
    assert sum(world.hits.values()) == 1  # one list page
