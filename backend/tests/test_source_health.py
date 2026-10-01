"""Pure derive_health unit tests (ADR-012 §11): no database, no wall clock."""

from datetime import UTC, datetime, timedelta

from app.enums import IngestionRunStatus
from app.services.source_health import derive_health

NOW = datetime(2040, 1, 1, tzinfo=UTC)


def test_never_run() -> None:
    health = derive_health(
        enabled=True,
        latest_finished_status=None,
        last_success_at=None,
        consecutive_failures=0,
        now=NOW,
    )
    assert health.health == "never_run"
    assert health.last_success_age_hours is None


def test_fresh_success_is_healthy() -> None:
    health = derive_health(
        enabled=True,
        latest_finished_status=IngestionRunStatus.SUCCESS,
        last_success_at=NOW - timedelta(hours=1),
        consecutive_failures=0,
        now=NOW,
    )
    assert health.health == "healthy"
    assert health.last_success_age_hours == 1.0


def test_no_change_counts_as_a_fresh_success() -> None:
    health = derive_health(
        enabled=True,
        latest_finished_status=IngestionRunStatus.NO_CHANGE,
        last_success_at=NOW - timedelta(hours=1),
        consecutive_failures=0,
        now=NOW,
    )
    assert health.health == "healthy"


def test_fresh_success_but_the_latest_run_already_failed() -> None:
    # The source succeeded recently, but the newest finished run after that was a failure.
    health = derive_health(
        enabled=True,
        latest_finished_status=IngestionRunStatus.FAILED,
        last_success_at=NOW - timedelta(hours=1),
        consecutive_failures=1,
        now=NOW,
    )
    assert health.health == "failing"


def test_repeated_failures_report_the_streak() -> None:
    health = derive_health(
        enabled=True,
        latest_finished_status=IngestionRunStatus.FAILED,
        last_success_at=NOW - timedelta(days=10),
        consecutive_failures=6,
        now=NOW,
    )
    assert health.health == "failing"
    assert health.consecutive_failures == 6


def test_stale_last_success() -> None:
    health = derive_health(
        enabled=True,
        latest_finished_status=IngestionRunStatus.SUCCESS,
        last_success_at=NOW - timedelta(hours=40),
        consecutive_failures=0,
        now=NOW,
    )
    assert health.health == "stale"


def test_warning_window_between_healthy_and_stale() -> None:
    health = derive_health(
        enabled=True,
        latest_finished_status=IngestionRunStatus.SUCCESS,
        last_success_at=NOW - timedelta(hours=30),
        consecutive_failures=0,
        now=NOW,
    )
    assert health.health == "warning"


def test_recovery_clears_the_streak() -> None:
    # A SUCCESS after failures resets last_success_at (the query's boundary) and the streak with
    # it; this only checks that derive_health reports whatever streak it's given rather than
    # inventing one from the failure history.
    health = derive_health(
        enabled=True,
        latest_finished_status=IngestionRunStatus.SUCCESS,
        last_success_at=NOW - timedelta(minutes=5),
        consecutive_failures=0,
        now=NOW,
    )
    assert health.health == "healthy"
    assert health.consecutive_failures == 0


def test_partial_is_never_reported_fully_healthy() -> None:
    health = derive_health(
        enabled=True,
        latest_finished_status=IngestionRunStatus.PARTIAL,
        last_success_at=NOW - timedelta(minutes=5),
        consecutive_failures=1,
        now=NOW,
    )
    assert health.health == "warning"


def test_partial_does_not_improve_an_already_stale_source() -> None:
    health = derive_health(
        enabled=True,
        latest_finished_status=IngestionRunStatus.PARTIAL,
        last_success_at=NOW - timedelta(hours=40),
        consecutive_failures=1,
        now=NOW,
    )
    assert health.health == "stale"


def test_disabled_overrides_everything() -> None:
    health = derive_health(
        enabled=False,
        latest_finished_status=IngestionRunStatus.FAILED,
        last_success_at=None,
        consecutive_failures=3,
        now=NOW,
    )
    assert health.health == "disabled"


def test_a_running_run_is_judged_by_the_finished_run_before_it() -> None:
    # The caller is responsible for passing the latest *finished* status, not RUNNING; this
    # confirms derive_health has no special RUNNING handling of its own to get wrong, and just
    # uses whatever finished status it's handed.
    health = derive_health(
        enabled=True,
        latest_finished_status=IngestionRunStatus.SUCCESS,
        last_success_at=NOW - timedelta(hours=2),
        consecutive_failures=0,
        now=NOW,
    )
    assert health.health == "healthy"


def test_never_succeeded_but_not_failed_is_failing() -> None:
    # e.g. the only finished run ever is PARTIAL: no success to measure an age from.
    health = derive_health(
        enabled=True,
        latest_finished_status=IngestionRunStatus.PARTIAL,
        last_success_at=None,
        consecutive_failures=1,
        now=NOW,
    )
    assert health.health == "failing"
