"""Command-line administration.

Owner accounts (ADR-007). There is no registration or reset endpoint:

    python -m app.cli create-owner --username NAME
    python -m app.cli set-password --username NAME

Passwords are read with getpass (never echoed) or, for automation with synthetic test
credentials, as one line from standard input (--password-stdin). Never as an argument.

Source sync (ADR-008), the same pipeline the API uses:

    python -m app.cli sync-sources             # every enabled source
    python -m app.cli sync-sources --scheduled # same, labeled for the scheduled GH Actions run
    python -m app.cli sync-source SOURCE       # one source, by ID or key (e.g. greenhouse:board)

Prints run counts and elapsed time only (never payloads, headers, or the database URL).

Exit codes: 0 every attempted source finished success/no_change/partial; 1 at least one source
failed; 2 an operational error before any source could be attempted (the database is unreachable
or misconfigured, or, with --scheduled, its schema isn't at this code's migration head).

Requirement candidate catalog scan (ADR-012 §9):

    python -m app.cli scan-requirements [--batch-size N]

Idempotent; never accepts, rejects, changes an assessment status, or evaluates. Prints counts
only. Exits 2 on an operational (database) error, never on an individual extractor failure.

Source coverage and discovery (ADR-013 §2, §9):

    python -m app.cli source-coverage

Derived on read; zero network calls, nothing stored. Prints aggregate counts only: coverage
metrics, provider distribution, and how many proven suggestions by kind are and aren't already
configured. Never a title, company name, payload, URL, or the database URL. Exits 2 on a
database error, like the other commands.
"""

import argparse
import getpass
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, select
from sqlalchemy.exc import ArgumentError, OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.enums import IngestionRunStatus
from app.ingestion.http import configured_transport
from app.ingestion.pipeline import SyncInProgress, sync_enabled_sources, sync_source
from app.models import AuthUser, IngestionRun, IngestionSource
from app.services import auth, source_discovery
from app.services.requirement_candidates import CATALOG_SCAN_BATCH_SIZE, scan_catalog

# Never the exception text or the URL it may embed (ADR-009 §9): a connection failure or a
# malformed DATABASE_URL both print this fixed, safe line instead.
DB_ERROR_MESSAGE = "error: couldn't reach or use the configured database."


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    password = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != password:
        raise auth.OwnerError("Passwords don't match.")
    return password


def _find_source(db: Session, reference: str) -> IngestionSource | None:
    try:
        return db.get(IngestionSource, uuid.UUID(reference))
    except ValueError:
        sources = db.scalars(select(IngestionSource)).all()
        return next((s for s in sources if s.key == reference.lower()), None)


def _elapsed(run: IngestionRun) -> str:
    if run.finished_at is None:
        return "?"
    return f"{(run.finished_at - run.started_at).total_seconds():.1f}s"


def _summary(run: IngestionRun) -> str:
    counts = ", ".join(
        f"{name} {getattr(run, f'{name}_count')}"
        for name in (
            "fetched",
            "created",
            "updated",
            "deduplicated",
            "unchanged",
            "closed",
            "reactivated",
            "invalid",
            "error",
        )
    )
    line = f"{run.source.key}: {run.status.value} ({counts}, elapsed {_elapsed(run)})"
    return f"{line}: {run.error_summary}" if run.error_summary else line


def _sync_source(reference: str) -> int:
    try:
        with Session(get_engine(), expire_on_commit=False) as db:
            source = _find_source(db, reference)
            if source is None:
                print(f"error: no source {reference!r}", file=sys.stderr)
                return 1
            try:
                run = sync_source(db, source, transport=configured_transport())
            except SyncInProgress as error:
                print(f"error: {error}", file=sys.stderr)
                return 1
            print(_summary(run))
            return 1 if run.status is IngestionRunStatus.FAILED else 0
    except (OperationalError, ArgumentError, RuntimeError):
        print(DB_ERROR_MESSAGE, file=sys.stderr)
        return 2


# backend/alembic, next to the `app` package (the scheduled workflow runs from backend/).
ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"
SCHEMA_BEHIND_MESSAGE = (
    "error: the database schema isn't at this code's migration head; migrate before syncing."
)


def schema_is_current(connection: Connection) -> bool:
    """Whether the database is at the code's single Alembic head. The scheduled sync checks this
    first: new code on an unmigrated database would fail item by item (a `partial` run, exit 0)
    instead of failing visibly."""
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    head = ScriptDirectory.from_config(config).get_current_head()
    return MigrationContext.configure(connection).get_current_revision() == head


def _sync_sources(*, scheduled: bool) -> int:
    started = time.monotonic()
    skipped: list[str] = []
    try:
        with Session(get_engine(), expire_on_commit=False) as db:
            if scheduled and not schema_is_current(db.connection()):
                print(SCHEMA_BEHIND_MESSAGE, file=sys.stderr)
                return 2
            runs = sync_enabled_sources(
                db,
                transport=configured_transport(),
                on_skip=lambda source: skipped.append(source.key),
            )
    except (OperationalError, ArgumentError, RuntimeError):
        print(DB_ERROR_MESSAGE, file=sys.stderr)
        return 2
    for run in runs:
        print(_summary(run))
    for key in skipped:
        print(f"{key}: skipped (already syncing)")
    failed = sum(1 for r in runs if r.status is IngestionRunStatus.FAILED)
    label = "scheduled sync" if scheduled else "sync"
    print(
        f"{label}: {len(runs)} run, {len(skipped)} skipped, {failed} failed,"
        f" elapsed {time.monotonic() - started:.1f}s"
    )
    return 1 if failed else 0


def _scan_requirements(batch_size: int) -> int:
    try:
        with Session(get_engine(), expire_on_commit=False) as db:
            result = scan_catalog(db, batch_size=batch_size)
    except (OperationalError, ArgumentError, RuntimeError):
        print(DB_ERROR_MESSAGE, file=sys.stderr)
        return 2
    print(
        f"scanned {result.scanned}, refreshed {result.refreshed}, unchanged {result.unchanged},"
        f" failed {result.failed}, candidates_created {result.candidates_created}"
    )
    return 0


def _source_coverage() -> int:
    try:
        with Session(get_engine(), expire_on_commit=False) as db:
            result = source_discovery.discover(db)
    except (OperationalError, ArgumentError, RuntimeError):
        print(DB_ERROR_MESSAGE, file=sys.stderr)
        return 2
    coverage = result.coverage
    pct = coverage.description_coverage_percent
    print(
        f"opportunities: {coverage.active_opportunities} open, "
        f"{coverage.with_description} with description, "
        f"{coverage.without_description} without "
        f"({pct if pct is not None else 'n/a'}% coverage)"
    )
    print(
        f"ats_backed {coverage.ats_backed}, feed_only {coverage.feed_only}, "
        f"enrichable {coverage.enrichable}, unsupported {coverage.unsupported}"
    )
    for provider in result.providers:
        print(
            f"provider {provider.provider}: {provider.opportunities} opportunities, "
            f"supported={provider.supported}, enrichable={provider.enrichable}"
        )
    configured = sum(1 for s in result.suggestions if s.already_configured)
    not_configured = len(result.suggestions) - configured
    print(
        f"suggestions: {len(result.suggestions)} total, "
        f"{configured} configured, {not_configured} not"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli", description="Owner account and source administration."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("create-owner", "create the single owner account"),
        ("set-password", "rotate a password and revoke that user's sessions"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--username", required=True)
        command.add_argument(
            "--password-stdin",
            action="store_true",
            help="read the password from standard input (automation with test credentials)",
        )
    all_sources = commands.add_parser("sync-sources", help="sync every enabled opportunity source")
    all_sources.add_argument(
        "--scheduled",
        action="store_true",
        help="label this run as the scheduled GitHub Actions sync (ADR-012 §10)",
    )
    one = commands.add_parser("sync-source", help="sync one opportunity source")
    one.add_argument("source", help="source ID or key, e.g. greenhouse:exampleboard")
    scan = commands.add_parser(
        "scan-requirements", help="refresh requirement candidates catalog-wide (ADR-012 §9)"
    )
    scan.add_argument("--batch-size", type=int, default=CATALOG_SCAN_BATCH_SIZE)
    commands.add_parser(
        "source-coverage", help="print ATS source coverage and discovery counts (ADR-013)"
    )
    args = parser.parse_args(argv)

    if args.command == "sync-sources":
        return _sync_sources(scheduled=args.scheduled)
    if args.command == "sync-source":
        return _sync_source(args.source)
    if args.command == "scan-requirements":
        return _scan_requirements(args.batch_size)
    if args.command == "source-coverage":
        return _source_coverage()

    action: Callable[[Session, str, str], AuthUser] = (
        auth.create_owner if args.command == "create-owner" else auth.set_password
    )
    try:
        password = _read_password(args.password_stdin)
        with Session(get_engine()) as db:
            action(db, args.username, password)
            db.commit()
    except auth.OwnerError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    done = "Created owner" if args.command == "create-owner" else "Password updated for"
    print(f"{done} {args.username!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
