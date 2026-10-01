"""Command-line administration.

Owner accounts (ADR-007). There is no registration or reset endpoint:

    python -m app.cli create-owner --username NAME
    python -m app.cli set-password --username NAME

Passwords are read with getpass (never echoed) or, for automation with synthetic test
credentials, as one line from standard input (--password-stdin). Never as an argument.

Source sync (ADR-008), the same pipeline the API uses:

    python -m app.cli sync-sources            # every enabled source
    python -m app.cli sync-source SOURCE      # one source, by ID or key (e.g. greenhouse:board)

Prints run counts only (never payloads). Exits 1 if a requested sync failed.

Requirement candidate catalog scan (ADR-012 §9):

    python -m app.cli scan-requirements [--batch-size N]

Idempotent; never accepts, rejects, changes an assessment status, or evaluates. Prints counts
only. Exits 1 only on an operational error (never on an individual extractor failure).
"""

import argparse
import getpass
import sys
import uuid
from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.enums import IngestionRunStatus
from app.ingestion.http import configured_transport
from app.ingestion.pipeline import SyncInProgress, sync_enabled_sources, sync_source
from app.models import AuthUser, IngestionRun, IngestionSource
from app.services import auth
from app.services.requirement_candidates import CATALOG_SCAN_BATCH_SIZE, scan_catalog


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
    line = f"{run.source.key}: {run.status.value} ({counts})"
    return f"{line}: {run.error_summary}" if run.error_summary else line


def _sync(reference: str | None) -> int:
    with Session(get_engine(), expire_on_commit=False) as db:
        if reference is None:
            runs = sync_enabled_sources(db, transport=configured_transport())
        else:
            source = _find_source(db, reference)
            if source is None:
                print(f"error: no source {reference!r}", file=sys.stderr)
                return 1
            try:
                runs = [sync_source(db, source, transport=configured_transport())]
            except SyncInProgress as error:
                print(f"error: {error}", file=sys.stderr)
                return 1
        for run in runs:
            print(_summary(run))
    return 1 if any(r.status is IngestionRunStatus.FAILED for r in runs) else 0


def _scan_requirements(batch_size: int) -> int:
    with Session(get_engine(), expire_on_commit=False) as db:
        result = scan_catalog(db, batch_size=batch_size)
    print(
        f"scanned {result.scanned}, refreshed {result.refreshed}, unchanged {result.unchanged},"
        f" failed {result.failed}, candidates_created {result.candidates_created}"
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
    commands.add_parser("sync-sources", help="sync every enabled opportunity source")
    one = commands.add_parser("sync-source", help="sync one opportunity source")
    one.add_argument("source", help="source ID or key, e.g. greenhouse:exampleboard")
    scan = commands.add_parser(
        "scan-requirements", help="refresh requirement candidates catalog-wide (ADR-012 §9)"
    )
    scan.add_argument("--batch-size", type=int, default=CATALOG_SCAN_BATCH_SIZE)
    args = parser.parse_args(argv)

    if args.command == "sync-sources":
        return _sync(None)
    if args.command == "sync-source":
        return _sync(args.source)
    if args.command == "scan-requirements":
        return _scan_requirements(args.batch_size)

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
