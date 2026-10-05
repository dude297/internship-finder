"""The shared ingestion pipeline against PostgreSQL: dedupe, idempotency, closure, partial and
failed runs, curation protection, and evaluation history. Synthetic payloads only."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx2
import pytest
from sqlalchemy import Engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import (
    ApplicationStatus,
    EducationLevel,
    EligibilityStatus,
    IngestionRunStatus,
    IngestionSourceKind,
    OpportunityType,
    RequirementsAssessmentStatus,
    RequirementType,
    SourceRegion,
    SourceScope,
)
from app.ingestion.adapters.community_feed import BUILTIN_IDENTIFIER
from app.ingestion.pipeline import SyncInProgress, sync_enabled_sources, sync_source
from app.models import (
    Application,
    IngestionRun,
    IngestionSource,
    Opportunity,
    OpportunityEvaluation,
    OpportunityIdentifier,
    OpportunityRequirement,
    OpportunitySourceRecord,
    Profile,
)
from app.models.ingestion import RUNNING_RUN_INDEX
from app.repositories import latest_evaluation
from app.schemas.sources import SourceUpdate
from app.services.sources import update_source
from tests.ingestion_fixtures import (
    ASHBY_BOARD,
    ASHBY_JOB_ID,
    ASHBY_URL,
    FEED_URL,
    GREENHOUSE_BOARD,
    GREENHOUSE_URL,
    LEVER_POSTING_ID,
    LEVER_SITE,
    LEVER_URL,
    FakeSource,
    ashby_board,
    ashby_job,
    feed,
    feed_job,
    greenhouse_board,
    greenhouse_job,
    lever_posting,
)

pytestmark = pytest.mark.postgres


def count(db: Session, model: type[Any]) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


@pytest.fixture
def web() -> FakeSource:
    return FakeSource()


@pytest.fixture
def feed_source(db: Session) -> IngestionSource:
    return db.scalars(
        select(IngestionSource).where(IngestionSource.identifier == BUILTIN_IDENTIFIER)
    ).one()


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


@pytest.fixture
def lever_source(db: Session) -> IngestionSource:
    source = IngestionSource(
        kind=IngestionSourceKind.LEVER,
        identifier=LEVER_SITE,
        region=SourceRegion.GLOBAL,
        display_name="Example Institute",
    )
    db.add(source)
    db.commit()
    return source


@pytest.fixture
def ashby_source(db: Session) -> IngestionSource:
    source = IngestionSource(
        kind=IngestionSourceKind.ASHBY,
        identifier=ASHBY_BOARD,
        display_name="Example Board Inc.",
    )
    db.add(source)
    db.commit()
    return source


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


def sync(db: Session, source: IngestionSource, web: FakeSource) -> IngestionRun:
    return sync_source(db, source, transport=web.transport())


def counts(run: IngestionRun) -> dict[str, int]:
    return {
        name: getattr(run, f"{name}_count")
        for name in (
            "fetched",
            "filtered",
            "created",
            "updated",
            "deduplicated",
            "unchanged",
            "closed",
            "reactivated",
            "invalid",
            "error",
        )
        if getattr(run, f"{name}_count")
    }


def record(db: Session, source: IngestionSource, external_id: str) -> OpportunitySourceRecord:
    return db.scalars(
        select(OpportunitySourceRecord).where(
            OpportunitySourceRecord.ingestion_source_id == source.id,
            OpportunitySourceRecord.external_id == external_id,
        )
    ).one()


JOB_A = feed_job("workday:example:/job/A")
JOB_B = feed_job("workday:example:/job/B", title="Synthetic Data Intern")


# --- First sync, idempotency, conditional requests ----------------------------------------------


def test_first_sync_imports_unassessed_opportunities_with_provenance(
    db: Session, feed_source: IngestionSource, web: FakeSource, profile: Profile
) -> None:
    web.json(FEED_URL, feed(JOB_A, JOB_B), headers={"ETag": '"v1"'})

    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.SUCCESS
    assert counts(run) == {"fetched": 2, "created": 2}
    assert run.normalized_count == 2
    assert run.source_generated_at == datetime(2040, 9, 21, 6, tzinfo=UTC)
    assert feed_source.etag == '"v1"' and feed_source.last_success_at is not None

    rec = record(db, feed_source, JOB_A["id"])
    opportunity = rec.opportunity
    assert opportunity.title == "Synthetic Engineering Intern"
    assert opportunity.opportunity_type is OpportunityType.INTERNSHIP
    assert opportunity.posted_at == datetime(2040, 9, 20, tzinfo=UTC)
    assert opportunity.manually_curated_at is None
    assert opportunity.requirements_assessment_status is RequirementsAssessmentStatus.UNASSESSED
    assert opportunity.requirements == []  # sponsorship never becomes a requirement
    assert rec.raw_payload == JOB_A
    assert rec.source_name == "community_feed:zshah-tech-internships"
    assert rec.is_active and rec.closed_at is None and rec.content_hash
    evaluation = latest_evaluation(db, profile.id, opportunity.id)
    assert evaluation is not None
    assert evaluation.eligibility_status is EligibilityStatus.NEEDS_VERIFICATION
    assert {(i.namespace, i.value) for i in opportunity.identifiers} == {
        ("zshah", JOB_A["id"]),
        ("url", JOB_A["url"]),
    }


def test_identical_second_sync_changes_nothing(
    db: Session, feed_source: IngestionSource, web: FakeSource, profile: Profile
) -> None:
    web.json(FEED_URL, feed(JOB_A, JOB_B))
    sync(db, feed_source, web)
    before = {
        m: count(db, m)
        for m in (
            Opportunity,
            OpportunitySourceRecord,
            OpportunityIdentifier,
            OpportunityEvaluation,
        )
    }
    first_seen = record(db, feed_source, JOB_A["id"]).last_seen_at

    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.SUCCESS
    assert counts(run) == {"fetched": 2, "unchanged": 2}
    after = {m: count(db, m) for m in before}
    assert after == before
    db.expire_all()
    assert record(db, feed_source, JOB_A["id"]).last_seen_at > first_seen


def test_not_modified_is_no_change(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    web.json(FEED_URL, feed(JOB_A), headers={"ETag": '"v1"', "Last-Modified": "Fri, 21 Sep 2040"})
    sync(db, feed_source, web)
    last_seen = record(db, feed_source, JOB_A["id"]).last_seen_at
    web.respond(FEED_URL, lambda _r: httpx2.Response(304))

    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.NO_CHANGE
    assert counts(run) == {}
    assert web.requests[-1].headers["If-None-Match"] == '"v1"'
    assert web.requests[-1].headers["If-Modified-Since"] == "Fri, 21 Sep 2040"
    db.expire_all()
    assert record(db, feed_source, JOB_A["id"]).last_seen_at == last_seen
    assert record(db, feed_source, JOB_A["id"]).is_active


# --- Updates, closure, reactivation -------------------------------------------------------------


def test_changed_item_updates_the_opportunity(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    web.json(FEED_URL, feed(JOB_A))
    sync(db, feed_source, web)
    web.json(FEED_URL, feed(JOB_A | {"title": "Renamed Synthetic Intern"}))

    run = sync(db, feed_source, web)

    assert counts(run) == {"fetched": 1, "updated": 1}
    rec = record(db, feed_source, JOB_A["id"])
    assert rec.opportunity.title == "Renamed Synthetic Intern"
    assert rec.raw_payload["title"] == "Renamed Synthetic Intern"


def test_missing_item_is_closed_not_deleted_and_can_return(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    web.json(FEED_URL, feed(JOB_A, JOB_B))
    sync(db, feed_source, web)
    opportunity_b = record(db, feed_source, JOB_B["id"]).opportunity
    opportunity_b.application = Application(status=ApplicationStatus.APPLIED, notes="Synthetic.")
    db.commit()

    web.json(FEED_URL, feed(JOB_A))
    closed = sync(db, feed_source, web)

    assert counts(closed) == {"fetched": 1, "unchanged": 1, "closed": 1}
    db.expire_all()
    rec_b = record(db, feed_source, JOB_B["id"])
    assert not rec_b.is_active and rec_b.closed_at is not None
    assert count(db, Opportunity) == 2  # nothing deleted
    assert rec_b.opportunity.application is not None
    assert rec_b.opportunity.application.notes == "Synthetic."

    web.json(FEED_URL, feed(JOB_A, JOB_B))
    back = sync(db, feed_source, web)

    assert counts(back) == {"fetched": 2, "unchanged": 2, "reactivated": 1}
    db.expire_all()
    rec_b = record(db, feed_source, JOB_B["id"])
    assert rec_b.is_active and rec_b.closed_at is None


def test_an_empty_complete_snapshot_closes_everything(
    db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1), greenhouse_job(2)))
    sync(db, gh_source, web)
    web.json(GREENHOUSE_URL, greenhouse_board())

    run = sync(db, gh_source, web)

    assert run.status is IngestionRunStatus.SUCCESS
    assert run.closed_count == 2


# --- Failures never close unseen records ---------------------------------------------------------


def _no_sleep(_seconds: float) -> None:
    pass


def _timeout(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectTimeout("synthetic", request=request)


FAILURES: dict[str, Callable[[httpx2.Request], httpx2.Response]] = {
    "timeout": _timeout,
    "rate_limited": lambda _r: httpx2.Response(429, headers={"Retry-After": "600"}),
    "http_error": lambda _r: httpx2.Response(500),
    "invalid_json": lambda _r: httpx2.Response(
        200, content=b"{", headers={"Content-Type": "application/json"}
    ),
    "schema_mismatch": lambda _r: httpx2.Response(200, json={"unexpected": []}),
    "incomplete_snapshot": lambda _r: httpx2.Response(200, json=feed(count=5)),
}


@pytest.mark.parametrize("code", sorted(FAILURES))
def test_failed_runs_change_nothing(
    db: Session,
    feed_source: IngestionSource,
    web: FakeSource,
    code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.ingestion.http.time.sleep", _no_sleep)
    web.json(FEED_URL, feed(JOB_A, JOB_B), headers={"ETag": '"v1"'})
    sync(db, feed_source, web)
    web.respond(FEED_URL, FAILURES[code])

    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.FAILED
    assert run.errors[0].code == code
    assert run.error_summary
    assert run.closed_count == 0
    db.expire_all()
    assert all(r.is_active for r in db.scalars(select(OpportunitySourceRecord)))
    assert feed_source.etag == '"v1"'  # validators only change on success


def test_oversized_response_fails_the_run(
    db: Session, feed_source: IngestionSource, web: FakeSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.ingestion.http.MAX_BYTES", 50)
    web.json(FEED_URL, feed(JOB_A))

    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.FAILED
    assert run.errors[0].code == "response_too_large"
    assert count(db, Opportunity) == 0


def test_one_malformed_item_is_a_partial_run_without_closures(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    web.json(FEED_URL, feed(JOB_A, JOB_B), headers={"ETag": '"v1"'})
    sync(db, feed_source, web)
    job_c = feed_job("workday:example:/job/C")
    web.json(
        FEED_URL,
        feed(job_c, feed_job("workday:example:/job/broken", title=None)),
        headers={"ETag": '"v2"'},
    )

    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.PARTIAL
    assert counts(run) == {"fetched": 2, "created": 1, "invalid": 1}
    assert [(e.stage.value, e.code, e.external_id) for e in run.errors] == [
        ("normalize", "invalid_item", "workday:example:/job/broken")
    ]
    db.expire_all()
    # A and B are missing from this snapshot, but a partial run never closes anything.
    assert all(r.is_active for r in db.scalars(select(OpportunitySourceRecord)))
    assert record(db, feed_source, job_c["id"]).opportunity is not None
    assert feed_source.etag == '"v1"'  # refetched in full next time


def test_duplicate_ids_in_one_snapshot_are_errors(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    web.json(FEED_URL, feed(JOB_A, JOB_A))

    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.PARTIAL
    assert counts(run) == {"fetched": 2, "created": 1, "error": 1}
    assert run.errors[0].code == "duplicate_item"


def test_errors_stored_per_run_are_capped(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    broken = [feed_job(f"broken-{n}", title=None) for n in range(130)]
    web.json(FEED_URL, feed(*broken))

    run = sync(db, feed_source, web)

    assert run.invalid_count == 130
    assert len(run.errors) == 100


def test_unexpected_persist_failure_rolls_back_only_that_item(
    db: Session, feed_source: IngestionSource, web: FakeSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.exc import DataError

    from app.ingestion import pipeline

    real = pipeline._write_canonical  # pyright: ignore[reportPrivateUsage]

    def flaky(opportunity: Opportunity, item: Any, source_type: Any) -> None:
        if item.external_id == JOB_B["id"]:
            raise DataError("synthetic", None, Exception("synthetic"))
        real(opportunity, item, source_type)

    monkeypatch.setattr(pipeline, "_write_canonical", flaky)
    web.json(FEED_URL, feed(JOB_A, JOB_B))

    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.PARTIAL
    assert counts(run) == {"fetched": 2, "created": 1, "error": 1}
    assert run.errors[0].code == "persist_failed"
    assert count(db, Opportunity) == 1 and count(db, OpportunitySourceRecord) == 1


# --- Cross-source deduplication -----------------------------------------------------------------


def test_feed_and_greenhouse_sightings_share_one_opportunity(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource, web: FakeSource
) -> None:
    feed_item = feed_job(
        f"greenhouse:{GREENHOUSE_BOARD}:1001",
        url="https://careers.example.com/robotics?gh_jid=1001",
    )
    web.json(FEED_URL, feed(feed_item))
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001)))

    sync(db, feed_source, web)
    run = sync(db, gh_source, web)

    assert counts(run) == {"fetched": 1, "deduplicated": 1}
    assert count(db, Opportunity) == 1
    [opportunity] = db.scalars(select(Opportunity)).all()
    assert {r.source_name for r in opportunity.source_records} == {
        "community_feed:zshah-tech-internships",
        f"greenhouse:{GREENHOUSE_BOARD}",
    }
    assert {i.namespace for i in opportunity.identifiers} == {"zshah", "greenhouse", "url"}
    assert count(db, OpportunityIdentifier) == 4  # the two different URLs are both kept

    again = sync(db, gh_source, web)
    assert counts(again) == {"fetched": 1, "unchanged": 1}
    assert count(db, Opportunity) == 1 and count(db, OpportunitySourceRecord) == 2


def test_only_one_record_rewrites_a_deduplicated_opportunity(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource, web: FakeSource
) -> None:
    """Two sources describing one posting differently (the feed has no description) must not
    overwrite each other on every change, or a reviewed posting keeps looking changed: exactly
    one owns the canonical fields (ADR-013 §1). The board outranks the feed and takes over as
    soon as it attaches (ADR-013 §4.3), so a feed change afterwards never flips the text back;
    only the owning board's own change does -- and that one does mark the review stale."""
    feed_item = feed_job(
        f"greenhouse:{GREENHOUSE_BOARD}:1001",
        url="https://careers.example.com/robotics?gh_jid=1001",
    )
    web.json(FEED_URL, feed(feed_item))
    web.json(
        GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content="Must be a U.S. citizen."))
    )
    sync(db, feed_source, web)
    sync(db, gh_source, web)
    [opportunity] = db.scalars(select(Opportunity)).all()
    assert opportunity.description == "Must be a U.S. citizen."  # the board owns on attach
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    db.commit()

    # An unrelated feed change (salary): the feed isn't the owner, so it never touches the text.
    web.json(FEED_URL, feed(feed_item | {"salary": "$25/hr"}))
    assert counts(sync(db, feed_source, web))["updated"] == 1
    db.refresh(opportunity)
    assert opportunity.description == "Must be a U.S. citizen."
    assert opportunity.requirements_stale_since is None
    assert opportunity.requirements_assessment_status is RequirementsAssessmentStatus.COMPLETE

    # The owning board's own change does rewrite the text, and does mark the review stale.
    web.json(
        GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content="Rewritten board text."))
    )
    assert counts(sync(db, gh_source, web))["updated"] == 1

    db.refresh(opportunity)
    assert opportunity.description == "Rewritten board text."
    assert opportunity.requirements_stale_since is not None
    assert opportunity.requirements_assessment_status is RequirementsAssessmentStatus.UNASSESSED


def test_lever_first_then_feed(
    db: Session, feed_source: IngestionSource, lever_source: IngestionSource, web: FakeSource
) -> None:
    web.json(LEVER_URL, [lever_posting()])
    feed_item = feed_job(
        f"lever:{LEVER_SITE}:{LEVER_POSTING_ID}",
        url=f"https://jobs.lever.co/{LEVER_SITE}/{LEVER_POSTING_ID}",
    )
    web.json(FEED_URL, feed(feed_item))

    sync(db, lever_source, web)
    run = sync(db, feed_source, web)

    assert counts(run) == {"fetched": 1, "deduplicated": 1}
    assert count(db, Opportunity) == 1
    # The first source's canonical content stays; the feed only adds provenance.
    assert db.scalars(select(Opportunity)).one().title == "Synthetic Research Intern"


def test_same_title_and_company_never_merge(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource, web: FakeSource
) -> None:
    web.json(FEED_URL, feed(feed_job("workday:example:/job/X", title="Synthetic Robotics Intern")))
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001)))

    sync(db, feed_source, web)
    sync(db, gh_source, web)

    assert count(db, Opportunity) == 2


def test_identity_conflict_is_recorded_and_changes_nothing(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource, web: FakeSource
) -> None:
    shared_url = "https://careers.example.com/robotics/role-7"
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(7)))
    sync(db, gh_source, web)  # opportunity X: greenhouse examplerobotics:7
    web.json(FEED_URL, feed(feed_job("workday:example:/job/Y", url=shared_url)))
    sync(db, feed_source, web)  # opportunity Y: url shared_url
    before = {
        m: count(db, m) for m in (Opportunity, OpportunitySourceRecord, OpportunityIdentifier)
    }

    # Points at X (greenhouse ID) and Y (URL) at once.
    conflicting = feed_job(f"greenhouse:{GREENHOUSE_BOARD}:7", url=shared_url)
    web.json(FEED_URL, feed(feed_job("workday:example:/job/Y", url=shared_url), conflicting))
    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.PARTIAL
    assert counts(run) == {"fetched": 2, "unchanged": 1, "error": 1}
    assert [(e.stage.value, e.code) for e in run.errors] == [("identify", "identity_conflict")]
    assert {m: count(db, m) for m in before} == before


def test_same_url_twice_in_one_source_is_not_merged(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    shared = "https://careers.example.com/internships/apply"
    web.json(
        FEED_URL,
        feed(feed_job("workday:a:/1", url=shared), feed_job("workday:a:/2", url=shared)),
    )

    run = sync(db, feed_source, web)

    assert counts(run) == {"fetched": 2, "created": 2}
    assert count(db, Opportunity) == 2
    assert run.status is IngestionRunStatus.SUCCESS
    assert counts(sync(db, feed_source, web)) == {"fetched": 2, "unchanged": 2}

    # The second one keeps updating: its own unchanged URL isn't a conflict.
    web.json(
        FEED_URL,
        feed(
            feed_job("workday:a:/1", url=shared),
            feed_job("workday:a:/2", url=shared, title="Synthetic Renamed Intern"),
        ),
    )
    again = sync(db, feed_source, web)
    assert again.status is IngestionRunStatus.SUCCESS
    assert counts(again) == {"fetched": 2, "updated": 1, "unchanged": 1}
    assert record(db, feed_source, "workday:a:/2").opportunity.title == "Synthetic Renamed Intern"


def _state(db: Session) -> dict[str, Any]:
    """Everything an ingested item can change, keyed so two snapshots compare exactly."""
    db.expire_all()
    return {
        "opportunities": {
            o.id: (o.title, o.application_url, o.last_seen_at)
            for o in db.scalars(select(Opportunity))
        },
        "records": {
            r.id: (r.opportunity_id, r.source_url, r.content_hash, r.is_active, r.last_seen_at)
            for r in db.scalars(select(OpportunitySourceRecord))
        },
        "identifiers": {
            (i.namespace, i.value): i.opportunity_id
            for i in db.scalars(select(OpportunityIdentifier))
        },
    }


def test_same_source_item_moving_onto_another_opportunitys_url_is_a_conflict(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    url_a = "https://careers.example.com/jobs/role-a"
    url_b = "https://careers.example.com/jobs/role-b"
    job_b = feed_job("workday:example:/job/B", url=url_b, title="Synthetic Data Intern")
    web.json(FEED_URL, feed(feed_job("workday:example:/job/A", url=url_a), job_b))
    sync(db, feed_source, web)
    before = _state(db)

    # A keeps its external ID but now claims B's URL: A's identity and B's at once.
    web.json(FEED_URL, feed(feed_job("workday:example:/job/A", url=url_b), job_b))
    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.PARTIAL
    assert counts(run) == {"fetched": 2, "unchanged": 1, "error": 1}
    assert [(e.stage.value, e.code, e.external_id) for e in run.errors] == [
        ("identify", "identity_conflict", "workday:example:/job/A")
    ]
    after = _state(db)
    # B was seen again (last_seen_at moves); A, its record, and every identifier are untouched.
    a = record(db, feed_source, "workday:example:/job/A")
    b = record(db, feed_source, "workday:example:/job/B")
    assert after["opportunities"][a.opportunity_id] == before["opportunities"][a.opportunity_id]
    assert after["records"][a.id] == before["records"][a.id]
    assert a.source_url == url_a
    assert after["identifiers"] == before["identifiers"]
    assert after["identifiers"][("url", url_b)] == b.opportunity_id
    assert {k: len(v) for k, v in after.items()} == {k: len(v) for k, v in before.items()}
    assert all(r.is_active for r in db.scalars(select(OpportunitySourceRecord)))


def test_same_source_item_gaining_another_opportunitys_provider_id_is_a_conflict(
    db: Session, feed_source: IngestionSource, lever_source: IngestionSource, web: FakeSource
) -> None:
    feed_id = f"lever:{LEVER_SITE}:{LEVER_POSTING_ID}"
    # Off jobs.lever.co, so no Lever identity yet: two separate opportunities.
    web.json(FEED_URL, feed(feed_job(feed_id, url="https://careers.example.com/jobs/lever-role")))
    sync(db, feed_source, web)
    web.json(LEVER_URL, [lever_posting()])
    sync(db, lever_source, web)
    assert count(db, Opportunity) == 2
    before = _state(db)

    # The feed item's URL moves onto jobs.lever.co: it now derives the Lever posting's identity.
    lever_url = f"https://jobs.lever.co/{LEVER_SITE}/{LEVER_POSTING_ID}"
    web.json(FEED_URL, feed(feed_job(feed_id, url=lever_url)))
    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.PARTIAL
    assert counts(run) == {"fetched": 1, "error": 1}
    assert [e.code for e in run.errors] == ["identity_conflict"]
    assert _state(db) == before


# --- Manual curation and evaluation -------------------------------------------------------------


def test_curated_opportunity_keeps_owner_content_but_provenance_updates(
    db: Session, feed_source: IngestionSource, web: FakeSource, profile: Profile
) -> None:
    web.json(FEED_URL, feed(JOB_A))
    sync(db, feed_source, web)
    opportunity = record(db, feed_source, JOB_A["id"]).opportunity
    opportunity.title = "Owner-Corrected Title"
    opportunity.description = "Owner notes on the posting."
    opportunity.start_date = date(2041, 6, 20)
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    opportunity.requirements = [
        OpportunityRequirement(
            requirement_type=RequirementType.MINIMUM_AGE,
            value={"years": 16},
            extraction_method="manual",
        )
    ]
    opportunity.manually_curated_at = datetime.now(UTC)
    db.commit()
    evaluations = count(db, OpportunityEvaluation)

    web.json(FEED_URL, feed(JOB_A | {"title": "Upstream Rename", "location": "Elsewhere"}))
    run = sync(db, feed_source, web)

    assert counts(run) == {"fetched": 1, "updated": 1}
    db.expire_all()
    rec = record(db, feed_source, JOB_A["id"])
    assert rec.raw_payload["title"] == "Upstream Rename"  # provenance updated
    kept = rec.opportunity
    assert kept.title == "Owner-Corrected Title"
    assert kept.description == "Owner notes on the posting."
    assert kept.location == "Example City"
    assert kept.start_date == date(2041, 6, 20)
    assert kept.requirements_assessment_status is RequirementsAssessmentStatus.COMPLETE
    assert [r.value for r in kept.requirements] == [{"years": 16}]
    assert count(db, OpportunityEvaluation) == evaluations


def test_only_changed_eligibility_or_fit_inputs_append_an_evaluation(
    db: Session, feed_source: IngestionSource, web: FakeSource, profile: Profile
) -> None:
    web.json(FEED_URL, feed(JOB_A))
    sync(db, feed_source, web)
    assert count(db, OpportunityEvaluation) == 1

    # Discovery metadata changes (the record updates) but no evaluation input does.
    web.json(FEED_URL, feed(JOB_A | {"salary": "$25/hr", "h1b_approvals": 99}))
    run = sync(db, feed_source, web)
    assert counts(run) == {"fetched": 1, "updated": 1}
    assert count(db, OpportunityEvaluation) == 1

    # The title is a fit input (ADR-010 §8): one new evaluation.
    web.json(FEED_URL, feed(JOB_A | {"title": "Renamed"}))
    sync(db, feed_source, web)
    assert count(db, OpportunityEvaluation) == 2

    # Re-syncing the same snapshot changes nothing.
    sync(db, feed_source, web)
    assert count(db, OpportunityEvaluation) == 2


def test_no_profile_means_no_evaluations(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    web.json(FEED_URL, feed(JOB_A))
    sync(db, feed_source, web)
    assert count(db, OpportunityEvaluation) == 0


# --- Run bookkeeping ----------------------------------------------------------------------------


def test_a_running_sync_blocks_a_second_one(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    db.add(
        IngestionRun(
            source=feed_source, status=IngestionRunStatus.RUNNING, started_at=datetime.now(UTC)
        )
    )
    db.commit()

    with pytest.raises(SyncInProgress):
        sync(db, feed_source, web)


def _running(source: IngestionSource) -> IngestionRun:
    return IngestionRun(
        source=source, status=IngestionRunStatus.RUNNING, started_at=datetime.now(UTC)
    )


def test_the_database_allows_one_running_run_per_source(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource
) -> None:
    first = _running(feed_source)
    db.add_all([first, _running(gh_source)])  # different sources may run at the same time
    db.commit()

    with pytest.raises(IntegrityError) as raised, db.begin_nested():
        db.add(_running(feed_source))
    assert raised.value.orig.diag.constraint_name == RUNNING_RUN_INDEX  # type: ignore[union-attr]

    # Once the run finishes, whatever its outcome, the source can run again.
    for status in (
        IngestionRunStatus.SUCCESS,
        IngestionRunStatus.PARTIAL,
        IngestionRunStatus.FAILED,
        IngestionRunStatus.NO_CHANGE,
    ):
        first.status = status
        first.finished_at = datetime.now(UTC)
        first = _running(feed_source)
        db.add(first)
        db.commit()
    assert count(db, IngestionRun) == 6


def test_a_start_that_loses_the_race_is_sync_in_progress(
    db: Session, pg_engine: Engine, feed_source: IngestionSource, web: FakeSource
) -> None:
    """Another session inserts its running run after this one's fast-path check found none;
    the unique index, not the check, turns this start into SyncInProgress."""
    web.json(FEED_URL, feed(JOB_A))
    source_id = feed_source.id  # read now: the cleanup below mustn't depend on this session

    def competitor_starts(_session: Session) -> None:
        with Session(pg_engine) as other:
            other.add(
                IngestionRun(
                    source_id=source_id,
                    status=IngestionRunStatus.RUNNING,
                    started_at=datetime.now(UTC),
                )
            )
            other.commit()

    event.listen(db, "before_commit", competitor_starts, once=True)
    try:
        with pytest.raises(SyncInProgress):
            sync(db, feed_source, web)
        assert count(db, Opportunity) == 0
        running = db.scalars(
            select(IngestionRun).where(IngestionRun.status == IngestionRunStatus.RUNNING)
        ).all()
        assert len(running) == 1  # only the competitor's
    finally:
        with Session(pg_engine) as other:  # committed outside the test transaction
            other.query(IngestionRun).filter(IngestionRun.source_id == source_id).delete()
            other.commit()


def test_an_abandoned_run_is_marked_failed(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    stale = IngestionRun(
        source=feed_source,
        status=IngestionRunStatus.RUNNING,
        started_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db.add(stale)
    db.commit()
    web.json(FEED_URL, feed(JOB_A))

    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.SUCCESS
    assert stale.status is IngestionRunStatus.FAILED and stale.finished_at is not None


def test_sync_enabled_sources_continues_past_a_failure(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource, web: FakeSource
) -> None:
    """Direct ATS sources sync before the discovery feed (ADR-013 §7), so the board (which is
    served) runs and succeeds before the feed (which isn't) fails; a disabled source never runs
    at all."""
    lever = IngestionSource(
        kind=IngestionSourceKind.LEVER,
        identifier="disabledsite",
        region=SourceRegion.EU,
        display_name="Disabled",
        enabled=False,
    )
    db.add(lever)
    db.commit()
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1)))  # the feed URL isn't served: 404

    runs = sync_enabled_sources(db, transport=web.transport())

    assert [(r.source.key, r.status) for r in runs] == [
        (f"greenhouse:{GREENHOUSE_BOARD}", IngestionRunStatus.SUCCESS),
        ("community_feed:zshah-tech-internships", IngestionRunStatus.FAILED),
    ]


def test_an_unexpected_failure_never_leaves_a_run_running(
    db: Session, feed_source: IngestionSource, web: FakeSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from app.ingestion import pipeline
    from app.ingestion.adapters import community_feed

    def explode(_payload: Any, _source: Any) -> Any:
        raise RuntimeError("synthetic adapter bug")

    broken = replace(community_feed.ADAPTER, parse=explode)

    def adapter_for(_kind: IngestionSourceKind) -> Any:
        return broken

    monkeypatch.setattr(pipeline, "adapter_for", adapter_for)
    web.json(FEED_URL, feed(JOB_A))

    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.FAILED
    assert run.errors[0].code == "internal_error"
    assert "synthetic adapter bug" not in (run.error_summary or "")
    assert count(db, Opportunity) == 0


def test_an_invalid_url_is_dropped_not_fatal(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    web.json(FEED_URL, feed(feed_job("a", url="https://careers.example.com:99999/x")))

    run = sync(db, feed_source, web)

    assert run.status is IngestionRunStatus.SUCCESS
    rec = record(db, feed_source, "a")
    assert rec.opportunity.application_url is None
    assert {i.namespace for i in rec.opportunity.identifiers} == {"zshah"}


# --- Source scope (ADR-010 §10) -----------------------------------------------------------------

FULL_TIME_GH = greenhouse_job(
    2002,
    title="Synthetic Staff Engineer",
    # Full-time postings often mention internships; the description is never searched.
    content="&lt;p&gt;Mentor our internship program.&lt;/p&gt;",
)


def conditional(body: Any, etag: str) -> Callable[[httpx2.Request], httpx2.Response]:
    """A provider that answers 304 whenever the request carries its current ETag."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        if request.headers.get("If-None-Match") == etag:
            return httpx2.Response(304)
        return httpx2.Response(200, json=body, headers={"ETag": etag})

    return handle


def set_scope(db: Session, source: IngestionSource, scope: SourceScope | None) -> None:
    update_source(source, SourceUpdate(display_name=source.display_name, enabled=True, scope=scope))
    db.commit()


def test_ats_sources_default_to_internships_only(
    db: Session,
    gh_source: IngestionSource,
    lever_source: IngestionSource,
    ashby_source: IngestionSource,
) -> None:
    feed = db.scalars(
        select(IngestionSource).where(IngestionSource.kind == IngestionSourceKind.COMMUNITY_FEED)
    ).one()
    assert gh_source.scope is SourceScope.INTERNSHIPS_ONLY
    assert lever_source.scope is SourceScope.INTERNSHIPS_ONLY
    assert ashby_source.scope is SourceScope.INTERNSHIPS_ONLY
    assert feed.scope is SourceScope.ALL


def test_greenhouse_internships_only_filters_by_title(
    db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(), FULL_TIME_GH))
    run = sync(db, gh_source, web)
    assert run.status is IngestionRunStatus.SUCCESS
    assert counts(run) == {"fetched": 2, "filtered": 1, "created": 1}
    assert run.normalized_count == 1
    assert [o.title for o in db.scalars(select(Opportunity))] == ["Synthetic Robotics Intern"]


def test_lever_internships_only_filters_by_title(
    db: Session, lever_source: IngestionSource, web: FakeSource
) -> None:
    full_time = lever_posting(
        "0a1b2c3d-0000-4000-8000-000000000002",
        text="Synthetic Account Executive",
        categories={"commitment": "Full-time", "location": "Example City"},
    )
    web.json(LEVER_URL, [lever_posting(), full_time])
    run = sync(db, lever_source, web)
    assert counts(run) == {"fetched": 2, "filtered": 1, "created": 1}
    assert [o.title for o in db.scalars(select(Opportunity))] == ["Synthetic Research Intern"]


def test_all_postings_scope_keeps_everything(
    db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    set_scope(db, gh_source, SourceScope.ALL)
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(), FULL_TIME_GH))
    assert counts(sync(db, gh_source, web)) == {"fetched": 2, "created": 2}


def test_builtin_feed_is_never_filtered(
    db: Session, feed_source: IngestionSource, web: FakeSource
) -> None:
    web.json(FEED_URL, feed(JOB_A | {"title": "Synthetic Software Engineer"}))
    assert counts(sync(db, feed_source, web)) == {"fetched": 1, "created": 1}
    with pytest.raises(ValueError, match="built-in"):
        set_scope(db, feed_source, SourceScope.INTERNSHIPS_ONLY)


def test_scope_change_forces_a_full_sync_that_closes_and_reactivates(
    db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    set_scope(db, gh_source, SourceScope.ALL)
    web.respond(
        GREENHOUSE_URL, conditional(greenhouse_board(greenhouse_job(), FULL_TIME_GH), '"v1"')
    )
    assert counts(sync(db, gh_source, web)) == {"fetched": 2, "created": 2}
    assert gh_source.etag == '"v1"'

    # Unchanged scope: the validators stay, so the provider's 304 is honored.
    set_scope(db, gh_source, None)
    assert sync(db, gh_source, web).status is IngestionRunStatus.NO_CHANGE

    # all → internships_only: validators cleared, full snapshot, the full-time posting closes.
    set_scope(db, gh_source, SourceScope.INTERNSHIPS_ONLY)
    assert (gh_source.etag, gh_source.last_modified) == (None, None)
    run = sync(db, gh_source, web)
    assert "If-None-Match" not in web.requests[-1].headers
    assert run.status is IngestionRunStatus.SUCCESS
    assert counts(run) == {"fetched": 2, "filtered": 1, "unchanged": 1, "closed": 1}
    staff = record(db, gh_source, "2002")
    assert not staff.is_active and staff.closed_at is not None
    assert count(db, Opportunity) == 2  # closed, never deleted

    # internships_only → all: full snapshot again, the posting comes back.
    set_scope(db, gh_source, SourceScope.ALL)
    run = sync(db, gh_source, web)
    assert counts(run) == {"fetched": 2, "unchanged": 2, "reactivated": 1}
    db.expire_all()
    assert record(db, gh_source, "2002").is_active


def test_filtered_items_do_not_evaluate(
    db: Session, gh_source: IngestionSource, web: FakeSource, profile: Profile
) -> None:
    web.json(GREENHOUSE_URL, greenhouse_board(FULL_TIME_GH))
    run = sync(db, gh_source, web)
    assert counts(run) == {"fetched": 1, "filtered": 1}
    assert count(db, OpportunityEvaluation) == 0


# --- Ashby (ADR-012 §12) -------------------------------------------------------------------------


def test_ashby_created_then_unchanged(
    db: Session, ashby_source: IngestionSource, web: FakeSource
) -> None:
    web.json(ASHBY_URL, ashby_board(ashby_job()))

    run = sync(db, ashby_source, web)
    assert run.status is IngestionRunStatus.SUCCESS
    assert counts(run) == {"fetched": 1, "created": 1}
    assert [o.title for o in db.scalars(select(Opportunity))] == ["Synthetic Data Science Intern"]

    again = sync(db, ashby_source, web)
    assert counts(again) == {"fetched": 1, "unchanged": 1}


def test_ashby_removed_posting_closes_on_a_complete_snapshot(
    db: Session, ashby_source: IngestionSource, web: FakeSource
) -> None:
    web.json(ASHBY_URL, ashby_board(ashby_job("a"), ashby_job("b")))
    sync(db, ashby_source, web)

    web.json(ASHBY_URL, ashby_board(ashby_job("a")))
    run = sync(db, ashby_source, web)

    assert run.status is IngestionRunStatus.SUCCESS
    assert counts(run) == {"fetched": 1, "unchanged": 1, "closed": 1}
    closed = record(db, ashby_source, "b")
    assert not closed.is_active and closed.closed_at is not None
    assert count(db, Opportunity) == 2  # closed, never deleted


def test_ashby_one_invalid_item_is_partial_and_closes_nothing(
    db: Session, ashby_source: IngestionSource, web: FakeSource
) -> None:
    web.json(ASHBY_URL, ashby_board(ashby_job("a"), ashby_job("b")))
    sync(db, ashby_source, web)

    bad = ashby_job("c", title=None)
    web.json(ASHBY_URL, ashby_board(ashby_job("a"), bad))
    run = sync(db, ashby_source, web)

    assert run.status is IngestionRunStatus.PARTIAL
    assert counts(run) == {"fetched": 2, "unchanged": 1, "invalid": 1}
    db.expire_all()
    # "b" wasn't in this (partial) snapshot at all, but a partial run never closes anything.
    assert record(db, ashby_source, "b").is_active


def test_ashby_posting_becoming_unlisted_closes_like_a_removed_posting(
    db: Session, ashby_source: IngestionSource, web: FakeSource
) -> None:
    web.json(ASHBY_URL, ashby_board(ashby_job()))
    sync(db, ashby_source, web)

    web.json(ASHBY_URL, ashby_board(ashby_job(isListed=False)))
    run = sync(db, ashby_source, web)

    assert run.status is IngestionRunStatus.SUCCESS
    assert run.closed_count == 1
    db.expire_all()
    closed = record(db, ashby_source, ASHBY_JOB_ID)
    assert not closed.is_active and closed.closed_at is not None


@pytest.mark.parametrize("bad", ["missing", "true", None])
def test_ashby_malformed_islisted_makes_the_run_partial_and_closes_nothing(
    db: Session, ashby_source: IngestionSource, web: FakeSource, bad: Any
) -> None:
    web.json(ASHBY_URL, ashby_board(ashby_job(), ashby_job("b")))
    sync(db, ashby_source, web)

    # Schema drift on one item: the valid one still processes, but nothing unseen closes.
    drifted = ashby_job("b")
    if bad == "missing":
        del drifted["isListed"]
    else:
        drifted["isListed"] = bad
    web.json(ASHBY_URL, ashby_board(ashby_job(), drifted))
    run = sync(db, ashby_source, web)

    assert run.status is IngestionRunStatus.PARTIAL
    assert run.closed_count == 0
    assert counts(run) == {"fetched": 2, "unchanged": 1, "invalid": 1}
    db.expire_all()
    assert record(db, ashby_source, ASHBY_JOB_ID).is_active
    assert record(db, ashby_source, "b").is_active


def test_ashby_islisted_dropped_board_wide_closes_nothing(
    db: Session, ashby_source: IngestionSource, web: FakeSource
) -> None:
    web.json(ASHBY_URL, ashby_board(ashby_job()))
    sync(db, ashby_source, web)

    job = ashby_job()
    del job["isListed"]
    web.json(ASHBY_URL, ashby_board(job))
    run = sync(db, ashby_source, web)

    assert run.status is IngestionRunStatus.PARTIAL
    assert run.closed_count == 0
    db.expire_all()
    assert record(db, ashby_source, ASHBY_JOB_ID).is_active


def test_ashby_internships_only_filters_by_title(
    db: Session, ashby_source: IngestionSource, web: FakeSource
) -> None:
    full_time = ashby_job(
        "full-time",
        title="Synthetic Staff Engineer",
        employmentType="FullTime",
    )
    web.json(ASHBY_URL, ashby_board(ashby_job(), full_time))
    run = sync(db, ashby_source, web)
    assert counts(run) == {"fetched": 2, "filtered": 1, "created": 1}
    assert [o.title for o in db.scalars(select(Opportunity))] == ["Synthetic Data Science Intern"]
