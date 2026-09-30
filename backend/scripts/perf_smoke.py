"""Catalog re-evaluation performance smoke (ADR-010 §9). Manual only, never in CI.

Seeds ~1,100 synthetic opportunities into a DISPOSABLE database, then times the operations the
owner triggers: the first Match Profile save (scores everything), an unchanged save, a changed
save, the recommended list query, and (Milestone 5) a résumé upload plus one review batch that
accepts every imported fact. Prints timings and SQL statement counts (to spot N+1).

    PERF_DATABASE_URL=postgresql+psycopg://…/if_perf python scripts/perf_smoke.py

The database is migrated to head and its opportunities and profile are replaced. Timings vary
by machine; they are reported, never asserted.
"""

import os
import sys
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, event
from sqlalchemy.orm import Session

from app.enums import (
    ExtractionMethod,
    OpportunityType,
    RemoteMode,
    RemotePreference,
    RequirementsAssessmentStatus,
    RequirementType,
)
from app.models import Opportunity, OpportunityRequirement, Profile, ProfileSource
from app.schemas.profile import MatchItem, MatchProfile
from app.schemas.profile_source import AcceptItem, ReviewRequest
from app.services.discovery import Filters, list_page
from app.services.match_profile import save_match_profile
from app.services.profile_sources import create_source, get_source, review_source

OPPORTUNITIES = 1_100
VOCABULARY = (
    "python sql machine learning robotics data science sensors embedded c++ javascript react "
    "research lab analysis statistics cloud kubernetes testing hardware firmware circuits "
    "biology chemistry design mentorship summer program students team collaborate build"
)
WORDS = VOCABULARY.split()


def description(n: int) -> str:
    # ~3,000 characters of synthetic text, varied per posting.
    return " ".join(WORDS[(n * 7 + i * 3) % len(WORDS)] for i in range(420))


RESUME = (
    "Skills\n" + ", ".join(f"Synthetic Skill {n}" for n in range(40)) + ", Robotics, SQL\n\n"
    "Relevant Coursework\nSynthetic Statistics, Synthetic Embedded Systems\n\n"
    "Projects\nSynthetic Sensor Array\n- Firmware for embedded sensors in C++\n"
).encode()


def seed(db: Session) -> None:
    db.execute(delete(ProfileSource))
    db.execute(delete(Opportunity))
    db.execute(delete(Profile))
    start = date(2041, 6, 1)
    for n in range(OPPORTUNITIES):
        db.add(
            Opportunity(
                title=f"Synthetic {WORDS[n % len(WORDS)].title()} Intern {n}",
                organization=f"Example Org {n % 40}",
                description=description(n),
                opportunity_type=OpportunityType.INTERNSHIP,
                application_url=f"https://example.org/jobs/{n}" if n % 3 else None,
                location=f"Example City {n % 12}",
                remote_mode=list(RemoteMode)[n % 3],
                start_date=start + timedelta(days=n % 60),
                end_date=start + timedelta(days=60 + n % 30),
                posted_at=datetime(2040, 9, 1, tzinfo=UTC) + timedelta(hours=n),
                requirements_assessment_status=list(RequirementsAssessmentStatus)[n % 3],
                requirements=[
                    OpportunityRequirement(
                        requirement_type=RequirementType.MINIMUM_AGE,
                        value={"years": 16 + n % 3},
                        extraction_method=ExtractionMethod.MANUAL,
                    )
                ]
                if n % 2
                else [],
            )
        )
    db.commit()


MATCH = MatchProfile(
    skills=["Python", "SQL", "C++", "React", "Kubernetes", "Statistics"],
    courses=["Data Science", "AP Calculus BC", "Intro to Robotics"],
    projects=[
        MatchItem(name="Synthetic Rover", description="Robotics sensors firmware embedded"),
        MatchItem(name="Synthetic Classifier", description="Machine learning python analysis"),
    ],
    interests=["robotics", "machine learning"],
    preferred_locations=["Example City 3"],
    remote_preference=RemotePreference.HYBRID_PREFERRED,
    availability_start=date(2041, 6, 1),
    availability_end=date(2041, 8, 31),
)


@contextmanager
def statements(db: Session) -> Generator[list[int]]:
    count = [0]

    def before(*_args: Any) -> None:
        count[0] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        yield count
    finally:
        event.remove(engine, "before_cursor_execute", before)


def timed(db: Session, label: str, action: Callable[[], object]) -> None:
    with statements(db) as count:
        started = time.perf_counter()
        result = action()
        db.commit()
        elapsed = time.perf_counter() - started
    print(f"{label:<34} {elapsed:6.2f} s  {count[0]:5d} SQL statements  {result}")


def main() -> None:
    url = os.environ.get("PERF_DATABASE_URL")
    if not url:
        sys.exit("Set PERF_DATABASE_URL to a disposable PostgreSQL database.")
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")

    with Session(create_engine(url)) as db:
        seed(db)
        print(f"{OPPORTUNITIES} synthetic opportunities")
        timed(db, "first Match Profile save", lambda: save_match_profile(db, MATCH))
        timed(db, "unchanged Match Profile save", lambda: save_match_profile(db, MATCH))
        changed = MATCH.model_copy(update={"skills": [*MATCH.skills, "Firmware"]})
        timed(db, "changed Match Profile save", lambda: save_match_profile(db, changed))
        for sort in ("recommended", "newest"):
            timed(
                db,
                f"{sort} list page (50)",
                lambda sort=sort: len(list_page(db, Filters(), 50, 0, sort)[0]),
            )
        timed(
            db,
            "recommended list, last page",
            lambda: len(list_page(db, Filters(), 50, OPPORTUNITIES - 50, "recommended")[0]),
        )
        detail = create_source(db, RESUME, "synthetic-resume.txt")
        db.commit()
        source = get_source(db, detail.id)
        assert source is not None
        batch = ReviewRequest(accept=[AcceptItem(id=fact.id) for fact in detail.facts])
        timed(
            db,
            f"review batch ({len(detail.facts)} accepted)",
            lambda: review_source(db, source, batch).evaluated_opportunities,
        )


if __name__ == "__main__":
    main()
