"""Owner bootstrap and source-sync CLI against PostgreSQL. Synthetic data only."""

import io
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import cli
from app.enums import IngestionRunStatus, IngestionSourceKind
from app.ingestion.pipeline import ABANDONED_AFTER
from app.models import AuthSession, AuthUser, IngestionRun, IngestionSource, Opportunity
from app.services import auth
from tests.ingestion_fixtures import FEED_URL, GREENHOUSE_BOARD, FakeSource, feed, feed_job

pytestmark = pytest.mark.postgres

PASSWORD = "synthetic-cli-password"


@pytest.fixture(autouse=True)
def cli_uses_test_transaction(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    # The CLI's own Session joins the test connection's transaction, which is rolled back.
    monkeypatch.setattr(cli, "get_engine", db.connection)


def run(monkeypatch: pytest.MonkeyPatch, *args: str, stdin: str = PASSWORD + "\n") -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return cli.main(list(args))


def owners(db: Session) -> list[AuthUser]:
    db.expire_all()
    return list(db.scalars(select(AuthUser)).all())


def test_create_owner_from_stdin(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(monkeypatch, "create-owner", "--username", "synthetic-owner", "--password-stdin")

    [user] = owners(db)
    out = capsys.readouterr()
    assert code == 0
    assert user.username == "synthetic-owner"
    assert user.is_active
    assert auth.verify_password(PASSWORD, user.password_hash)
    assert PASSWORD not in out.out + out.err  # never printed


def test_create_owner_interactively_uses_getpass(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts: list[str] = []

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return PASSWORD

    monkeypatch.setattr(cli.getpass, "getpass", fake_getpass)

    assert cli.main(["create-owner", "--username", "synthetic-owner"]) == 0
    assert prompts == ["Password: ", "Repeat password: "]
    assert len(owners(db)) == 1


def test_interactive_mismatch_is_refused(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([PASSWORD, PASSWORD + "-typo"])

    def fake_getpass(_prompt: str) -> str:
        return next(answers)

    monkeypatch.setattr(cli.getpass, "getpass", fake_getpass)

    assert cli.main(["create-owner", "--username", "synthetic-owner"]) == 1
    assert owners(db) == []


def test_duplicate_owner_is_refused(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    run(monkeypatch, "create-owner", "--username", "synthetic-owner", "--password-stdin")

    code = run(monkeypatch, "create-owner", "--username", "another-owner", "--password-stdin")

    assert code == 1
    assert [u.username for u in owners(db)] == ["synthetic-owner"]


@pytest.mark.parametrize(
    ("username", "password"),
    [("synthetic-owner", "too-short"), ("x", PASSWORD), ("has space", PASSWORD)],
)
def test_invalid_owner_input_is_refused(
    db: Session, monkeypatch: pytest.MonkeyPatch, username: str, password: str
) -> None:
    code = run(
        monkeypatch, "create-owner", "--username", username, "--password-stdin", stdin=password
    )

    assert code == 1
    assert owners(db) == []


def test_set_password_rotates_and_revokes_sessions(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run(monkeypatch, "create-owner", "--username", "synthetic-owner", "--password-stdin")
    [user] = owners(db)
    auth.start_session(db, user, timedelta(hours=1))
    db.commit()

    new_password = "synthetic-rotated-password"
    code = run(
        monkeypatch,
        "set-password",
        "--username",
        "synthetic-owner",
        "--password-stdin",
        stdin=new_password,
    )

    [user] = owners(db)
    assert code == 0
    assert auth.verify_password(new_password, user.password_hash)
    assert not auth.verify_password(PASSWORD, user.password_hash)
    assert db.scalars(select(AuthSession)).all() == []


def test_set_password_for_unknown_user_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    assert run(monkeypatch, "set-password", "--username", "nobody", "--password-stdin") == 1


def test_password_is_not_a_command_line_option() -> None:
    with pytest.raises(SystemExit):
        cli.main(["create-owner", "--username", "synthetic-owner", "--password", PASSWORD])


# --- Source sync --------------------------------------------------------------------------------


def use_fake_network(monkeypatch: pytest.MonkeyPatch, web: FakeSource) -> None:
    monkeypatch.setattr(cli, "configured_transport", web.transport)


def test_sync_source_by_key_prints_counts_only(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    web = FakeSource()
    web.json(FEED_URL, feed(feed_job("a"), feed_job("b")))
    use_fake_network(monkeypatch, web)

    code = cli.main(["sync-source", "community_feed:zshah-tech-internships"])

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("community_feed:zshah-tech-internships: success (fetched 2, created 2,")
    assert "Synthetic Engineering Intern" not in out  # never payloads
    assert len(db.scalars(select(Opportunity)).all()) == 2


def test_sync_source_by_id_and_failure_exit_code(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use_fake_network(monkeypatch, FakeSource())  # everything 404s
    source = db.scalars(select(IngestionSource)).one()

    code = cli.main(["sync-source", str(source.id)])

    assert code == 1
    assert "failed" in capsys.readouterr().out


def test_sync_sources_runs_every_enabled_source(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    web = FakeSource()
    web.json(FEED_URL, feed(feed_job("a")))
    use_fake_network(monkeypatch, web)

    assert cli.main(["sync-sources"]) == 0
    assert "success" in capsys.readouterr().out


def test_sync_unknown_source(monkeypatch: pytest.MonkeyPatch) -> None:
    use_fake_network(monkeypatch, FakeSource())
    assert cli.main(["sync-source", "greenhouse:nothing"]) == 1


def test_disabled_source_is_not_synced(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    web = FakeSource()
    web.json(FEED_URL, feed(feed_job("a")))
    use_fake_network(monkeypatch, web)
    builtin = db.scalars(select(IngestionSource)).one()
    builtin.enabled = False
    db.commit()

    code = cli.main(["sync-sources"])

    out = capsys.readouterr().out
    assert code == 0  # nothing attempted, nothing failed
    assert builtin.key not in out
    assert "0 run, 0 skipped, 0 failed" in out


def test_one_source_fails_others_continue_and_exit_code_is_one(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    web = FakeSource()
    web.json(FEED_URL, feed(feed_job("a")))  # the feed succeeds; greenhouse (unseeded) 404s
    use_fake_network(monkeypatch, web)
    db.add(
        IngestionSource(
            kind=IngestionSourceKind.GREENHOUSE,
            identifier=GREENHOUSE_BOARD,
            display_name="Example Robotics",
        )
    )
    db.commit()

    code = cli.main(["sync-sources", "--scheduled"])

    out = capsys.readouterr().out
    assert code == 1
    assert "community_feed:zshah-tech-internships: success" in out
    assert f"greenhouse:{GREENHOUSE_BOARD}: failed" in out
    assert "scheduled sync: 2 run, 0 skipped, 1 failed" in out


def test_a_source_already_running_is_skipped_and_reported(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use_fake_network(monkeypatch, FakeSource())
    builtin = db.scalars(select(IngestionSource)).one()
    db.add(
        IngestionRun(
            source=builtin, status=IngestionRunStatus.RUNNING, started_at=datetime.now(UTC)
        )
    )
    db.commit()

    code = cli.main(["sync-sources"])

    out = capsys.readouterr().out
    assert code == 0
    assert f"{builtin.key}: skipped (already syncing)" in out
    assert "0 run, 1 skipped, 0 failed" in out


def test_an_abandoned_running_run_is_repaired_and_the_source_still_syncs(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    web = FakeSource()
    web.json(FEED_URL, feed(feed_job("a")))
    use_fake_network(monkeypatch, web)
    builtin = db.scalars(select(IngestionSource)).one()
    stale = IngestionRun(
        source=builtin,
        status=IngestionRunStatus.RUNNING,
        started_at=datetime.now(UTC) - ABANDONED_AFTER - timedelta(minutes=1),
    )
    db.add(stale)
    db.commit()

    code = cli.main(["sync-sources"])

    db.expire_all()
    out = capsys.readouterr().out
    assert code == 0
    assert "already syncing" not in out  # the stale run was repaired, not treated as in progress
    assert "1 run, 0 skipped, 0 failed" in out
    assert stale.status is IngestionRunStatus.FAILED


def test_database_unreachable_exits_two_without_leaking_the_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    password = "synthetic-unreachable-password"  # test-only, never a real credential
    broken = create_engine(
        f"postgresql+psycopg://synthetic_user:{password}@127.0.0.1:1/if_m6_unreachable"
        "?connect_timeout=2"
    )
    monkeypatch.setattr(cli, "get_engine", lambda: broken)

    code = cli.main(["sync-sources"])

    out = capsys.readouterr()
    assert code == 2
    combined = out.out + out.err
    assert password not in combined
    assert "if_m6_unreachable" not in combined
    assert combined.strip() == cli.DB_ERROR_MESSAGE


def test_scheduled_sync_refuses_a_database_behind_the_code(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Merged code on an unmigrated database must fail the workflow visibly (exit 2), not run a
    sync whose items all fail into a `partial` run that exits 0."""

    def behind(_connection: object) -> bool:
        return False

    monkeypatch.setattr(cli, "schema_is_current", behind)
    web = FakeSource()
    web.json(FEED_URL, feed(feed_job("a")))
    use_fake_network(monkeypatch, web)

    code = cli.main(["sync-sources", "--scheduled"])

    captured = capsys.readouterr()
    assert code == 2
    assert "migration head" in captured.err
    assert db.scalars(select(IngestionRun)).first() is None  # nothing was attempted


def test_schema_check_matches_the_migrated_test_database(db: Session) -> None:
    assert cli.schema_is_current(db.connection())
