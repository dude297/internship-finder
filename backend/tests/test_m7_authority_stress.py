"""Canonical-owner stress tests (ADR-013 §1, §4, §5): same-tier stability under alternating
sync order, repeated takeover/fallback loops, closure/reopen, curation protection, and partial
runs inside a loop. Real DB rows, synthetic payloads only; see tests/ingestion_fixtures.py."""

from datetime import UTC, date, datetime
from typing import Any

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
)
from app.ingestion.adapters.community_feed import BUILTIN_IDENTIFIER
from app.models import IngestionSource, Opportunity, Profile
from app.repositories import latest_evaluation
from app.services.discovery import provenance
from tests.ingestion_fixtures import (
    ASHBY_BOARD,
    ASHBY_URL,
    FEED_URL,
    GREENHOUSE_BOARD,
    GREENHOUSE_URL,
    FakeSource,
    ashby_board,
    ashby_job,
    feed,
    feed_job,
    greenhouse_board,
    greenhouse_job,
)
from tests.test_ingestion import count, record, sync

pytestmark = pytest.mark.postgres

SHARED_URL = "https://careers.example.com/robotics/shared-posting"
GREENHOUSE_BOARD_2 = "examplerobotics2"
GREENHOUSE_URL_2 = (
    f"https://boards-api.greenhouse.io/v1/boards/{GREENHOUSE_BOARD_2}/jobs?content=true"
)
CITIZENSHIP_SENTENCE = "Must be a U.S. citizen."
FEED_TITLE = "Feed Title Intern"
BOARD_TITLE = "Board Title Intern"


@pytest.fixture
def web() -> FakeSource:
    return FakeSource()


@pytest.fixture
def feed_source(db: Session) -> IngestionSource:
    return db.scalars(
        select(IngestionSource).where(IngestionSource.identifier == BUILTIN_IDENTIFIER)
    ).one()


def _source(db: Session, kind: IngestionSourceKind, identifier: str) -> IngestionSource:
    source = IngestionSource(kind=kind, identifier=identifier, display_name=identifier)
    db.add(source)
    db.commit()
    return source


@pytest.fixture
def gh_source(db: Session) -> IngestionSource:
    return _source(db, IngestionSourceKind.GREENHOUSE, GREENHOUSE_BOARD)


@pytest.fixture
def gh2_source(db: Session) -> IngestionSource:
    return _source(db, IngestionSourceKind.GREENHOUSE, GREENHOUSE_BOARD_2)


@pytest.fixture
def ashby_source(db: Session) -> IngestionSource:
    return _source(db, IngestionSourceKind.ASHBY, ASHBY_BOARD)


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


def _eligibility(db: Session, profile: Profile, opportunity: Opportunity) -> EligibilityStatus:
    evaluation = latest_evaluation(db, profile.id, opportunity.id)
    assert evaluation is not None
    return evaluation.eligibility_status


def _is_open(opportunity: Opportunity) -> bool:
    return provenance(list(opportunity.source_records))[1] == "open"


def _gh(
    job_id: int = 1001, title: str = BOARD_TITLE, content: str = CITIZENSHIP_SENTENCE
) -> dict[str, Any]:
    return greenhouse_job(job_id, title=title, content=content, absolute_url=SHARED_URL)


def _feed_item(title: str = FEED_TITLE) -> dict[str, Any]:
    return feed_job(f"greenhouse:{GREENHOUSE_BOARD}:1001", title=title, url=SHARED_URL)


def _canonical(o: Opportunity) -> tuple[object, ...]:
    return (
        o.title,
        o.organization,
        o.description,
        o.opportunity_type,
        o.application_url,
        o.location,
        o.remote_mode,
        o.posted_at,
    )


# --- 1. Same tier, alternating sync order ---------------------------------------------------------

ORDERS = ["abc", "cba", "abababccaa", "bac"]


def test_same_tier_owner_never_changes_under_alternating_sync_order(
    db: Session,
    gh_source: IngestionSource,
    gh2_source: IngestionSource,
    ashby_source: IngestionSource,
    web: FakeSource,
) -> None:
    """Three direct ATS boards (two Greenhouse, one Ashby) naming one posting through a shared
    URL. A syncs first, so its record is the earliest and owns the canonical fields; across many
    rounds of changing text and every ordering the opportunity's title and description are
    always A's last-synced values, never B's or C's."""
    sources = {"a": gh_source, "b": gh2_source, "c": ashby_source}
    state = {"a": "A text 0", "b": "B text 0", "c": "C text 0"}

    def publish(key: str) -> None:
        if key == "a":
            job = greenhouse_job(
                1001, title="A Intern", content=state[key], absolute_url=SHARED_URL
            )
            web.json(GREENHOUSE_URL, greenhouse_board(job))
        elif key == "b":
            job = greenhouse_job(
                2001, title="B Intern", content=state[key], absolute_url=SHARED_URL
            )
            web.json(GREENHOUSE_URL_2, greenhouse_board(job))
        else:
            job = ashby_job(title="C Intern", descriptionPlain=state[key], jobUrl=SHARED_URL)
            web.json(ASHBY_URL, ashby_board(job))

    for key in "abc":  # establishes A as the earliest record
        publish(key)
        sync(db, sources[key], web)
    opportunity = db.scalars(select(Opportunity)).one()
    assert (opportunity.title, opportunity.description) == ("A Intern", "A text 0")

    synced_a = state["a"]
    for round_number in range(10):
        for key in "abc":
            state[key] = f"{key.upper()} text {round_number + 1}"
        for key in ORDERS[round_number % len(ORDERS)]:
            publish(key)
            run = sync(db, sources[key], web)
            assert run.status is IngestionRunStatus.SUCCESS
            if key == "a":
                synced_a = state["a"]
            db.refresh(opportunity)
            assert (opportunity.title, opportunity.description) == ("A Intern", synced_a)
            assert opportunity.application_url == SHARED_URL

    assert count(db, Opportunity) == 1
    assert len(opportunity.source_records) == 3
    assert all(r.is_active for r in opportunity.source_records)


def test_earliest_active_ats_reclaims_ownership_when_it_returns(
    db: Session, gh_source: IngestionSource, gh2_source: IngestionSource, web: FakeSource
) -> None:
    """The earliest board closes and the later one takes over; when the earliest returns it
    owns again (same tier: earliest first_seen_at wins), and the later board's own changes never
    move ownership. 10 rounds."""
    web.json(GREENHOUSE_URL, greenhouse_board(_gh(1001, "A Intern", "A text")))
    sync(db, gh_source, web)
    web.json(GREENHOUSE_URL_2, greenhouse_board(_gh(2001, "B Intern", "B text")))
    sync(db, gh2_source, web)
    opportunity = db.scalars(select(Opportunity)).one()

    for round_number in range(10):
        web.json(GREENHOUSE_URL, greenhouse_board())
        sync(db, gh_source, web)
        db.refresh(opportunity)
        assert (opportunity.title, opportunity.description) == (
            "B Intern",
            "B text" if round_number == 0 else f"B text {round_number - 1}",
        )
        assert _is_open(opportunity)

        web.json(GREENHOUSE_URL, greenhouse_board(_gh(1001, "A Intern", "A text")))
        sync(db, gh_source, web)
        db.refresh(opportunity)
        assert (opportunity.title, opportunity.description) == ("A Intern", "A text")

        # The later board changing its text while A owns changes nothing canonical.
        web.json(
            GREENHOUSE_URL_2, greenhouse_board(_gh(2001, "B Intern", f"B text {round_number}"))
        )
        sync(db, gh2_source, web)
        db.refresh(opportunity)
        assert (opportunity.title, opportunity.description) == ("A Intern", "A text")

    assert count(db, Opportunity) == 1


# --- 2. Takeover / fallback loops -----------------------------------------------------------------


def test_repeated_ats_close_and_return_loops_keep_one_open_pending_opportunity(
    db: Session,
    feed_source: IngestionSource,
    gh_source: IngestionSource,
    web: FakeSource,
    profile: Profile,
) -> None:
    web.json(FEED_URL, feed(_feed_item()))
    sync(db, feed_source, web)
    web.json(GREENHOUSE_URL, greenhouse_board(_gh()))
    sync(db, gh_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    eligibility = _eligibility(db, profile, opportunity)
    assert opportunity.title == BOARD_TITLE

    for loop in range(10):
        # The feed's own text changes while the board owns: recorded, never canonical.
        feed_title = f"{FEED_TITLE} v{loop}"
        web.json(FEED_URL, feed(_feed_item(feed_title)))
        sync(db, feed_source, web)
        db.refresh(opportunity)
        assert opportunity.title == BOARD_TITLE

        web.json(GREENHOUSE_URL, greenhouse_board())
        assert sync(db, gh_source, web).closed_count == 1
        db.refresh(opportunity)
        assert _is_open(opportunity)  # the feed still lists it
        assert opportunity.title == feed_title  # feed owns, from its latest stored item
        assert opportunity.description == CITIZENSHIP_SENTENCE  # kept, not erased

        web.json(GREENHOUSE_URL, greenhouse_board(_gh()))
        assert sync(db, gh_source, web).reactivated_count == 1
        db.refresh(opportunity)
        assert opportunity.title == BOARD_TITLE  # the board owns again

        assert count(db, Opportunity) == 1
        assert opportunity.requirements_assessment_status is (
            RequirementsAssessmentStatus.UNASSESSED
        )
        assert opportunity.requirements == []
        assert opportunity.requirement_candidates
        assert {c.review_state for c in opportunity.requirement_candidates} == {
            FactReviewState.PENDING
        }
        assert _eligibility(db, profile, opportunity) == eligibility

    assert len(opportunity.source_records) == 2
    assert all(r.is_active for r in opportunity.source_records)


# --- 3. Closure / reopen, and curation ----------------------------------------------------------


def _loop_everything(
    db: Session,
    feed_source: IngestionSource,
    gh_source: IngestionSource,
    web: FakeSource,
    opportunity: Opportunity,
) -> None:
    """Closes both sources, reopens the feed alone, then the board, three times."""
    for _ in range(3):
        web.json(GREENHOUSE_URL, greenhouse_board())
        sync(db, gh_source, web)
        web.json(FEED_URL, feed())
        sync(db, feed_source, web)
        db.refresh(opportunity)
        assert not _is_open(opportunity)

        web.json(FEED_URL, feed(_feed_item()))
        sync(db, feed_source, web)
        db.refresh(opportunity)
        assert _is_open(opportunity)

        web.json(GREENHOUSE_URL, greenhouse_board(_gh()))
        sync(db, gh_source, web)
        db.refresh(opportunity)
        assert _is_open(opportunity)


def test_everything_closes_the_opportunity_and_the_feed_alone_reopens_it(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource, web: FakeSource
) -> None:
    web.json(FEED_URL, feed(_feed_item()))
    sync(db, feed_source, web)
    web.json(GREENHOUSE_URL, greenhouse_board(_gh()))
    sync(db, gh_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    assert opportunity.title == BOARD_TITLE

    web.json(GREENHOUSE_URL, greenhouse_board())
    sync(db, gh_source, web)
    web.json(FEED_URL, feed())
    sync(db, feed_source, web)
    db.refresh(opportunity)
    assert not _is_open(opportunity)
    assert opportunity.title == FEED_TITLE  # last fallback text kept, not blanked
    assert opportunity.description == CITIZENSHIP_SENTENCE

    web.json(FEED_URL, feed(_feed_item("Feed Title Intern Reopened")))
    run = sync(db, feed_source, web)
    assert run.reactivated_count == 1
    db.refresh(opportunity)
    assert _is_open(opportunity)
    assert opportunity.title == "Feed Title Intern Reopened"  # the feed is the sole owner
    assert opportunity.description == CITIZENSHIP_SENTENCE
    assert record(db, gh_source, "1001").is_active is False

    web.json(GREENHOUSE_URL, greenhouse_board(_gh(content="Board is back.")))
    sync(db, gh_source, web)
    db.refresh(opportunity)
    assert (opportunity.title, opportunity.description) == (BOARD_TITLE, "Board is back.")
    assert count(db, Opportunity) == 1


def test_closure_reopen_loops_never_rewrite_a_curated_opportunity(
    db: Session, feed_source: IngestionSource, gh_source: IngestionSource, web: FakeSource
) -> None:
    web.json(FEED_URL, feed(_feed_item()))
    sync(db, feed_source, web)
    web.json(GREENHOUSE_URL, greenhouse_board(_gh()))
    sync(db, gh_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    opportunity.manually_curated_at = datetime.now(UTC)
    opportunity.title = "Owner-Curated Title"
    opportunity.description = "Owner-curated description."
    db.commit()
    frozen = _canonical(opportunity)

    _loop_everything(db, feed_source, gh_source, web, opportunity)
    # Source text changes on top of the loops are ignored too.
    web.json(GREENHOUSE_URL, greenhouse_board(_gh(title="Changed", content="Changed text.")))
    sync(db, gh_source, web)
    web.json(FEED_URL, feed(_feed_item("Changed feed title")))
    sync(db, feed_source, web)

    db.refresh(opportunity)
    assert _canonical(opportunity) == frozen
    assert opportunity.manually_curated_at is not None
    assert count(db, Opportunity) == 1


# --- 4. Partial ATS runs inside a loop ------------------------------------------------------------


def test_partial_ats_runs_inside_the_loop_never_close_or_hand_off_ownership(
    db: Session,
    feed_source: IngestionSource,
    gh_source: IngestionSource,
    web: FakeSource,
    profile: Profile,
) -> None:
    web.json(FEED_URL, feed(_feed_item()))
    sync(db, feed_source, web)
    web.json(GREENHOUSE_URL, greenhouse_board(_gh()))
    sync(db, gh_source, web)
    opportunity = db.scalars(select(Opportunity)).one()
    eligibility = _eligibility(db, profile, opportunity)
    bad_item = {"id": 9999, "absolute_url": None}  # invalid: makes any run PARTIAL

    for loop in range(5):
        # Partial run that omits the job: nothing closes, the board still owns.
        web.json(GREENHOUSE_URL, greenhouse_board(bad_item))
        run = sync(db, gh_source, web)
        assert run.status is IngestionRunStatus.PARTIAL
        assert run.closed_count == 0
        db.refresh(opportunity)
        assert (opportunity.title, opportunity.description) == (BOARD_TITLE, CITIZENSHIP_SENTENCE)

        # A complete run closes it: the feed falls back.
        web.json(GREENHOUSE_URL, greenhouse_board())
        sync(db, gh_source, web)
        db.refresh(opportunity)
        assert opportunity.title == FEED_TITLE
        assert _is_open(opportunity)

        # The job returns inside a partial run: the item still reactivates and re-owns.
        text = f"Returned in a partial run {loop}."
        web.json(GREENHOUSE_URL, greenhouse_board(_gh(content=text), bad_item))
        run = sync(db, gh_source, web)
        assert run.status is IngestionRunStatus.PARTIAL
        assert run.reactivated_count == 1
        db.refresh(opportunity)
        assert (opportunity.title, opportunity.description) == (BOARD_TITLE, text)
        assert record(db, gh_source, "1001").is_active

        web.json(GREENHOUSE_URL, greenhouse_board(_gh()))
        sync(db, gh_source, web)  # complete again, back to the baseline text

    assert count(db, Opportunity) == 1
    assert opportunity.requirements_assessment_status is RequirementsAssessmentStatus.UNASSESSED
    assert {c.review_state for c in opportunity.requirement_candidates} == {FactReviewState.PENDING}
    assert _eligibility(db, profile, opportunity) == eligibility
