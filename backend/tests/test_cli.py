"""Owner bootstrap and source-sync CLI against PostgreSQL. Synthetic data only."""

import io
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cli
from app.models import AuthSession, AuthUser, IngestionSource, Opportunity
from app.services import auth
from tests.ingestion_fixtures import FEED_URL, FakeSource, feed, feed_job

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
