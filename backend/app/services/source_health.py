"""Source health (ADR-012 §11): derived on read from existing run history, nothing new stored.

A pure function so it's tested without a database or the wall clock.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.enums import IngestionRunStatus

SourceHealthStatus = Literal["never_run", "healthy", "warning", "stale", "failing", "disabled"]

# A fresh success is healthy for a day; the next 12 hours are a warning (the twice-daily
# schedule should have run again by then); anything older is stale. These give one full missed
# cycle of slack over the twice-daily production schedule before escalating past "warning".
HEALTHY_WITHIN_HOURS = 24.0
WARNING_WITHIN_HOURS = 36.0


@dataclass(frozen=True)
class SourceHealth:
    health: SourceHealthStatus
    consecutive_failures: int
    last_success_age_hours: float | None


def derive_health(
    *,
    enabled: bool,
    latest_finished_status: IngestionRunStatus | None,
    last_success_at: datetime | None,
    consecutive_failures: int,
    now: datetime,
) -> SourceHealth:
    """`latest_finished_status` is the status of the newest run that isn't still RUNNING (None
    when the source has never finished a run); a RUNNING run in progress is judged by whatever
    finished before it, which is the point of passing that status in rather than the source's
    raw latest run."""
    age = None if last_success_at is None else (now - last_success_at).total_seconds() / 3600

    if not enabled:
        return SourceHealth("disabled", consecutive_failures, age)
    if latest_finished_status is None:
        return SourceHealth("never_run", consecutive_failures, age)
    if latest_finished_status is IngestionRunStatus.FAILED:
        return SourceHealth("failing", consecutive_failures, age)

    if age is None:
        health: SourceHealthStatus = "failing"
    elif age <= HEALTHY_WITHIN_HOURS:
        health = "healthy"
    elif age <= WARNING_WITHIN_HOURS:
        health = "warning"
    else:
        health = "stale"

    # A partial run is degraded data even with a recent success: never report it as fully healthy.
    if latest_finished_status is IngestionRunStatus.PARTIAL and health == "healthy":
        health = "warning"

    return SourceHealth(health, consecutive_failures, age)
