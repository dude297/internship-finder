"""Source authority (ADR-013): which automated record owns an opportunity's canonical fields,
takeover on dedup, the fallback when an ATS source closes, curation protection, and sync
ordering. Synthetic payloads only; see tests/ingestion_fixtures.py."""

import uuid
from datetime import UTC, date, datetime

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import (
    EducationLevel,
    EligibilityStatus,
    FactReviewState,
    IngestionRunStatus,
    IngestionSourceKind,
    RequirementsAssessmentStatus,
    RequirementType,
    SourceRegion,
)
from app.ingestion.adapters.community_feed import BUILTIN_IDENTIFIER
from app.ingestion.pipeline import sync_enabled_sources
from app.models import (
    IngestionSource,
    Opportunity,
    OpportunityEvaluation,
    OpportunityRequirement,
    Profile,
)
from app.repositories import latest_evaluation
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
from tests.test_ingestion import count, counts, record, sync  # plain helpers, not fixtures

pytestmark = pytest.mark.postgres


# --- Fixtures (duplicated from test_ingestion.py: pytest doesn't discover fixtures imported
# into another test module by name, and importing them only as parameter annotations reads as
# an unused import to the linter) ----------------------------------------------------------------


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
        kind=IngestionSourceKind.ASHBY, identifier=ASHBY_BOARD, display_name="Example Board Inc."
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


CITIZENSHIP_SENTENCE = "Must be a U.S. citizen."
GREENHOUSE_BOARD_2 = "examplerobotics2"
GREENHOUSE_URL_2 = (
    f"https://boards-api.greenhouse.io/v1/boards/{GREENHOUSE_BOARD_2}/jobs?content=true"
)


def _eligibility(
    db: Session, profile_id: uuid.UUID, opportunity_id: uuid.UUID
) -> EligibilityStatus:
    evaluation = latest_evaluation(db, profile_id, opportunity_id)
    assert evaluation is not None
    return evaluation.eligibility_status


# --- Takeover: a board enriches an existing feed opportunity -----------------------------------


def test_greenhouse_takeover_enriches_an_existing_feed_opportunity(
    db: Session,
    feed_source: IngestionSource,
    gh_source: IngestionSource,
    web: FakeSource,
    profile: Profile,
) -> None:
    """A Greenhouse board naming the same posting attaches and, outranking the feed, becomes the
    owner immediately (ADR-013 §4.3): one opportunity, two records, the board's description
    populated, and a pending requirement candidate -- without touching the assessment or
    eligibility (ADR-013 §6)."""
    feed_item = feed_job(
        f"greenhouse:{GREENHOUSE_BOARD}:1001",
        url="https://careers.example.com/robotics?gh_jid=1001",
    )
    web.json(FEED_URL, feed(feed_item))
    sync(db, feed_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    before = _eligibility(db, profile.id, opportunity.id)
    assert opportunity.description is None

    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content=CITIZENSHIP_SENTENCE)))
    run = sync(db, gh_source, web)

    assert counts(run) == {"fetched": 1, "deduplicated": 1}
    assert count(db, Opportunity) == 1
    db.refresh(opportunity)
    assert {r.source_name for r in opportunity.source_records} == {
        "community_feed:zshah-tech-internships",
        f"greenhouse:{GREENHOUSE_BOARD}",
    }
    assert opportunity.description == CITIZENSHIP_SENTENCE
    [candidate] = opportunity.requirement_candidates
    assert candidate.requirement_type is RequirementType.CITIZENSHIP
    assert candidate.review_state is FactReviewState.PENDING
    assert opportunity.requirements_assessment_status is RequirementsAssessmentStatus.UNASSESSED
    assert _eligibility(db, profile.id, opportunity.id) == before


def test_lever_takeover_enriches_an_existing_feed_opportunity(
    db: Session,
    feed_source: IngestionSource,
    lever_source: IngestionSource,
    web: FakeSource,
    profile: Profile,
) -> None:
    feed_id = f"lever:{LEVER_SITE}:{LEVER_POSTING_ID}"
    feed_item = feed_job(feed_id, url=f"https://jobs.lever.co/{LEVER_SITE}/{LEVER_POSTING_ID}")
    web.json(FEED_URL, feed(feed_item))
    sync(db, feed_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    before = _eligibility(db, profile.id, opportunity.id)
    assert opportunity.description is None

    web.json(
        LEVER_URL,
        [lever_posting(description=f"<p>{CITIZENSHIP_SENTENCE}</p>", lists=[], additional="")],
    )
    run = sync(db, lever_source, web)

    assert counts(run) == {"fetched": 1, "deduplicated": 1}
    db.refresh(opportunity)
    assert opportunity.description == CITIZENSHIP_SENTENCE
    [candidate] = opportunity.requirement_candidates
    assert candidate.requirement_type is RequirementType.CITIZENSHIP
    assert opportunity.requirements_assessment_status is RequirementsAssessmentStatus.UNASSESSED
    assert _eligibility(db, profile.id, opportunity.id) == before


def test_ashby_takeover_enriches_an_existing_feed_opportunity(
    db: Session,
    feed_source: IngestionSource,
    ashby_source: IngestionSource,
    web: FakeSource,
    profile: Profile,
) -> None:
    feed_id = f"ashby:{ASHBY_BOARD}:{ASHBY_JOB_ID}"
    feed_item = feed_job(feed_id, url=f"https://jobs.ashbyhq.com/{ASHBY_BOARD}/{ASHBY_JOB_ID}")
    web.json(FEED_URL, feed(feed_item))
    sync(db, feed_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    before = _eligibility(db, profile.id, opportunity.id)
    assert opportunity.description is None

    web.json(ASHBY_URL, ashby_board(ashby_job(descriptionPlain=CITIZENSHIP_SENTENCE)))
    run = sync(db, ashby_source, web)

    assert counts(run) == {"fetched": 1, "deduplicated": 1}
    db.refresh(opportunity)
    assert opportunity.description == CITIZENSHIP_SENTENCE
    [candidate] = opportunity.requirement_candidates
    assert candidate.requirement_type is RequirementType.CITIZENSHIP
    assert opportunity.requirements_assessment_status is RequirementsAssessmentStatus.UNASSESSED
    assert _eligibility(db, profile.id, opportunity.id) == before


# --- Fallback when the ATS record closes --------------------------------------------------------


def test_fallback_and_return_cycle_causes_no_staleness_or_extra_evaluation(
    db: Session,
    feed_source: IngestionSource,
    gh_source: IngestionSource,
    web: FakeSource,
    profile: Profile,
) -> None:
    """When the board closes, the feed (still active) takes over in the same run (ADR-013 §5);
    when the board reopens, it's the owner again (§4.2). Repeating the cycle never duplicates
    the opportunity, never loses the kept description, and -- because the feed and the board
    agree on every other canonical field here too -- never marks anything stale or adds a fit
    evaluation (fit also reads location, URL, and posted date, not just title and description)."""
    title = "Synthetic Engineering Intern"
    shared_url = "https://careers.example.com/robotics/shared-posting"
    posted_at = "2040-09-20T00:00:00Z"
    feed_item = feed_job(
        f"greenhouse:{GREENHOUSE_BOARD}:1001",
        title=title,
        url=shared_url,
        posted_at=posted_at,
    )
    gh_job = greenhouse_job(
        1001,
        title=title,
        content=CITIZENSHIP_SENTENCE,
        absolute_url=shared_url,
        first_published=posted_at,
    )
    web.json(FEED_URL, feed(feed_item))
    sync(db, feed_source, web)
    web.json(GREENHOUSE_URL, greenhouse_board(gh_job))
    sync(db, gh_source, web)

    opportunity = db.scalars(select(Opportunity)).one()
    assert opportunity.description == CITIZENSHIP_SENTENCE
    evaluations_after_takeover = count(db, OpportunityEvaluation)

    for _ in range(3):
        web.json(GREENHOUSE_URL, greenhouse_board())
        closed_run = sync(db, gh_source, web)
        assert closed_run.closed_count == 1
        assert count(db, Opportunity) == 1
        db.refresh(opportunity)
        assert opportunity.title == title
        assert opportunity.description == CITIZENSHIP_SENTENCE  # kept, not erased
        assert opportunity.application_url == shared_url
        assert opportunity.requirements_stale_since is None

        web.json(GREENHOUSE_URL, greenhouse_board(gh_job))
        reopened_run = sync(db, gh_source, web)
        assert reopened_run.reactivated_count == 1
        assert count(db, Opportunity) == 1
        db.refresh(opportunity)
        assert opportunity.title == title
        assert opportunity.description == CITIZENSHIP_SENTENCE
        assert opportunity.requirements_stale_since is None

    assert count(db, OpportunityEvaluation) == evaluations_after_takeover


def test_fallback_applies_even_when_the_feed_then_answers_not_modified(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource, web: FakeSource
) -> None:
    """The fallback doesn't depend on the feed's own sync re-deriving anything: it already
    happened in the ATS run (ADR-013 §5), so a feed sync that gets a bare 304 afterwards changes
    nothing further."""
    feed_item = feed_job(
        f"greenhouse:{GREENHOUSE_BOARD}:1001",
        url="https://careers.example.com/robotics?gh_jid=1001",
    )
    web.json(FEED_URL, feed(feed_item), headers={"ETag": '"v1"'})
    sync(db, feed_source, web)
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content=CITIZENSHIP_SENTENCE)))
    sync(db, gh_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    assert opportunity.description == CITIZENSHIP_SENTENCE

    web.json(GREENHOUSE_URL, greenhouse_board())
    run = sync(db, gh_source, web)
    assert run.closed_count == 1
    db.refresh(opportunity)
    assert opportunity.title == feed_item["title"]

    web.respond(FEED_URL, lambda _r: httpx2.Response(304))
    feed_run = sync(db, feed_source, web)

    assert feed_run.status is IngestionRunStatus.NO_CHANGE
    db.refresh(opportunity)
    assert opportunity.title == feed_item["title"]
    assert opportunity.description == CITIZENSHIP_SENTENCE


def test_fallback_skips_a_stored_payload_that_no_longer_normalizes(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource, web: FakeSource
) -> None:
    """A stored raw item that no longer normalizes (its adapter's schema tightened since it was
    stored) is logged and skipped; the run still succeeds and the opportunity keeps its current
    text (ADR-013 §5)."""
    feed_item = feed_job(
        f"greenhouse:{GREENHOUSE_BOARD}:1001",
        url="https://careers.example.com/robotics?gh_jid=1001",
    )
    web.json(FEED_URL, feed(feed_item))
    sync(db, feed_source, web)
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content=CITIZENSHIP_SENTENCE)))
    sync(db, gh_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    assert opportunity.description == CITIZENSHIP_SENTENCE

    feed_record = record(db, feed_source, feed_item["id"])
    feed_record.raw_payload = feed_record.raw_payload | {"title": None}  # breaks the feed schema
    db.commit()

    web.json(GREENHOUSE_URL, greenhouse_board())
    run = sync(db, gh_source, web)

    assert run.status is IngestionRunStatus.SUCCESS
    assert run.closed_count == 1
    db.refresh(opportunity)
    assert opportunity.description == CITIZENSHIP_SENTENCE  # kept; no valid new owner
    assert opportunity.title == "Synthetic Robotics Intern"  # the board's own last text stays


def test_ats_takeover_of_a_reviewed_feed_opportunity_marks_it_stale(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource, web: FakeSource
) -> None:
    """Enriching a posting the owner already reviewed on the feed's title alone marks it stale
    (ADR-013 §6): the text the review was based on changed. Accepted requirements are kept."""
    feed_item = feed_job(
        f"greenhouse:{GREENHOUSE_BOARD}:1001",
        url="https://careers.example.com/robotics?gh_jid=1001",
    )
    web.json(FEED_URL, feed(feed_item))
    sync(db, feed_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    opportunity.requirements_assessment_status = RequirementsAssessmentStatus.COMPLETE
    opportunity.requirements = [
        OpportunityRequirement(
            requirement_type=RequirementType.MINIMUM_AGE,
            value={"years": 18},
            extraction_method="manual",
        )
    ]
    db.commit()

    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content=CITIZENSHIP_SENTENCE)))
    run = sync(db, gh_source, web)

    assert counts(run) == {"fetched": 1, "deduplicated": 1}
    db.refresh(opportunity)
    assert opportunity.requirements_stale_since is not None
    assert opportunity.requirements_assessment_status is RequirementsAssessmentStatus.PARTIAL
    assert [r.value for r in opportunity.requirements] == [{"years": 18}]  # accepted, kept


# --- Two ATS sources on one opportunity -----------------------------------------------------------


def test_earliest_ats_wins_and_the_next_takes_over_when_it_closes(
    db: Session, gh_source: IngestionSource, web: FakeSource
) -> None:
    """Two boards naming one posting (sharing its public URL): the earliest active one owns, and
    the later board's own changes never alternate the text (ADR-013 §1). When the earliest
    closes, the only remaining active automated record takes over."""
    second = IngestionSource(
        kind=IngestionSourceKind.GREENHOUSE,
        identifier=GREENHOUSE_BOARD_2,
        display_name="Example Robotics 2",
    )
    db.add(second)
    db.commit()
    shared_url = "https://careers.example.com/robotics/shared-posting"

    web.json(
        GREENHOUSE_URL,
        greenhouse_board(
            greenhouse_job(1001, absolute_url=shared_url, content="First board text.")
        ),
    )
    sync(db, gh_source, web)
    web.json(
        GREENHOUSE_URL_2,
        greenhouse_board(
            greenhouse_job(2001, absolute_url=shared_url, content="Second board text.")
        ),
    )
    sync(db, second, web)

    [opportunity] = db.scalars(select(Opportunity)).all()
    assert opportunity.description == "First board text."  # the earlier board still owns

    web.json(
        GREENHOUSE_URL_2,
        greenhouse_board(
            greenhouse_job(2001, absolute_url=shared_url, content="Second board text, revised.")
        ),
    )
    sync(db, second, web)
    db.refresh(opportunity)
    assert opportunity.description == "First board text."  # never alternates

    web.json(GREENHOUSE_URL, greenhouse_board())
    run = sync(db, gh_source, web)

    assert run.closed_count == 1
    db.refresh(opportunity)
    assert opportunity.description == "Second board text, revised."  # the sole remaining owner


# --- Curation and flip-flop protection -----------------------------------------------------------


def test_curated_opportunity_is_never_rewritten_by_takeover_or_fallback(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource, web: FakeSource
) -> None:
    feed_item = feed_job(
        f"greenhouse:{GREENHOUSE_BOARD}:1001",
        url="https://careers.example.com/robotics?gh_jid=1001",
    )
    web.json(FEED_URL, feed(feed_item))
    sync(db, feed_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    opportunity.manually_curated_at = datetime.now(UTC)
    opportunity.title = "Owner-Curated Title"
    db.commit()

    # Would otherwise take over on attach (ADR-013 §4.3).
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content=CITIZENSHIP_SENTENCE)))
    sync(db, gh_source, web)
    db.refresh(opportunity)
    assert opportunity.title == "Owner-Curated Title"
    assert opportunity.description is None

    # Would otherwise trigger the fallback (ADR-013 §5).
    web.json(GREENHOUSE_URL, greenhouse_board())
    sync(db, gh_source, web)
    db.refresh(opportunity)
    assert opportunity.title == "Owner-Curated Title"
    assert opportunity.description is None


def test_no_flip_flop_across_repeated_unchanged_syncs_of_both_sources(
    db: Session,
    feed_source: IngestionSource,
    gh_source: IngestionSource,
    web: FakeSource,
    profile: Profile,
) -> None:
    feed_item = feed_job(
        f"greenhouse:{GREENHOUSE_BOARD}:1001",
        url="https://careers.example.com/robotics?gh_jid=1001",
    )
    web.json(FEED_URL, feed(feed_item))
    sync(db, feed_source, web)
    web.json(GREENHOUSE_URL, greenhouse_board(greenhouse_job(1001, content=CITIZENSHIP_SENTENCE)))
    sync(db, gh_source, web)

    opportunity = db.scalars(select(Opportunity)).one()
    evaluations = count(db, OpportunityEvaluation)
    description = opportunity.description

    for _ in range(3):
        assert counts(sync(db, feed_source, web)) == {"fetched": 1, "unchanged": 1}
        assert counts(sync(db, gh_source, web)) == {"fetched": 1, "unchanged": 1}

    db.refresh(opportunity)
    assert opportunity.description == description
    assert count(db, OpportunityEvaluation) == evaluations


# --- Scheduled-sync ordering --------------------------------------------------------------------


def test_sync_enabled_sources_runs_ats_before_the_feed_and_a_failure_never_blocks_others(
    db: Session,
    feed_source: IngestionSource,
    gh_source: IngestionSource,
    lever_source: IngestionSource,
    web: FakeSource,
) -> None:
    web.json(FEED_URL, feed())
    web.json(GREENHOUSE_URL, greenhouse_board())
    web.respond(LEVER_URL, lambda _r: httpx2.Response(500))  # a failing source

    runs = sync_enabled_sources(db, transport=web.transport())

    assert len(runs) == 3
    by_source = {run.source_id: run for run in runs}
    assert by_source[lever_source.id].status is IngestionRunStatus.FAILED
    assert by_source[gh_source.id].status is IngestionRunStatus.SUCCESS
    assert by_source[feed_source.id].status is IngestionRunStatus.SUCCESS
    requested = [str(r.url) for r in web.requests]
    assert requested.index(GREENHOUSE_URL) < requested.index(FEED_URL)
    assert requested.index(LEVER_URL) < requested.index(FEED_URL)
