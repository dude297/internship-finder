"""Version-bump staleness and the `reevaluate` command (ADR-018). Synthetic data only."""

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import app.repositories as repositories
from app import cli
from app.enums import RequirementType
from app.models import OpportunityEvaluation
from app.opportunities.eligibility.schemas import OpportunityInput, ProfileInput, RequirementInput
from app.repositories import eligibility_fingerprint, evaluate_catalog, evaluation_context
from tests.test_persistence import make_opportunity, make_profile, requirement

EDU = {"levels": ["undergraduate"], "accepts_incoming": True}


def test_rules_version_is_part_of_the_eligibility_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = ProfileInput.model_validate(make_profile())
    opportunity = OpportunityInput(start_date=date(2041, 9, 1))
    reqs = [RequirementInput(requirement_type=RequirementType.EDUCATION, value=EDU)]
    base = eligibility_fingerprint(profile, opportunity, reqs)

    monkeypatch.setattr(repositories, "RULES_VERSION", "v-next")

    assert eligibility_fingerprint(profile, opportunity, reqs) != base


def seed(db: Session) -> None:
    db.add(make_profile())
    with_education = make_opportunity(title="Education-gated")
    with_education.requirements = [requirement(RequirementType.EDUCATION, EDU)]
    age_only = make_opportunity(title="Age-gated")
    age_only.requirements = [requirement(RequirementType.MINIMUM_AGE, {"years": 16})]
    db.add_all([with_education, age_only])
    db.flush()


def evaluation_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(OpportunityEvaluation)) or 0


@pytest.mark.postgres
def test_rules_version_bump_makes_every_opportunity_stale(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(db)
    context = evaluation_context(db)
    assert context is not None
    assert evaluate_catalog(db, context).evaluated == 2
    assert evaluate_catalog(db, context).evaluated == 0

    monkeypatch.setattr(repositories, "RULES_VERSION", "v-next")
    dry = evaluate_catalog(db, context, dry_run=True)
    assert (dry.evaluated, dry.unchanged) == (2, 0)
    assert evaluation_count(db) == 2  # a dry run writes nothing

    second = evaluate_catalog(db, context)

    assert (second.evaluated, second.unchanged) == (2, 0)
    assert evaluation_count(db) == 4  # history appended, nothing overwritten
    assert evaluate_catalog(db, context).evaluated == 0


@pytest.mark.postgres
def test_scoring_version_bump_makes_every_opportunity_stale(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(db)
    context = evaluation_context(db)
    assert context is not None
    evaluate_catalog(db, context)

    monkeypatch.setattr(repositories, "SCORING_VERSION", "v-next")

    assert evaluate_catalog(db, context).evaluated == 2


@pytest.fixture
def cli_uses_test_transaction(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "get_engine", db.connection)


@pytest.mark.postgres
@pytest.mark.usefixtures("cli_uses_test_transaction")
def test_reevaluate_command(db: Session, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["reevaluate"]) == 0
    assert "no profile" in capsys.readouterr().out

    seed(db)
    assert cli.main(["reevaluate", "--dry-run"]) == 0
    assert capsys.readouterr().out.strip() == "would evaluate 2, unchanged 0"
    assert evaluation_count(db) == 0

    assert cli.main(["reevaluate", "--stale-only", "--batch-size", "1"]) == 0
    assert capsys.readouterr().out.strip() == "evaluated 2, unchanged 0"
    assert evaluation_count(db) == 2

    assert cli.main(["reevaluate"]) == 0
    assert capsys.readouterr().out.strip() == "evaluated 0, unchanged 2"


@pytest.mark.postgres
@pytest.mark.usefixtures("cli_uses_test_transaction")
def test_reevaluate_unexpected_error_prints_only_the_class_name(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seed(db)

    def boom(*args: object, **kwargs: object) -> None:
        raise ValueError("secret-ish")

    monkeypatch.setattr(cli, "evaluate_catalog", boom)

    assert cli.main(["reevaluate"]) == 1
    captured = capsys.readouterr()
    assert "ValueError" in captured.err
    assert "secret-ish" not in captured.err + captured.out


def test_reevaluate_exits_2_on_a_database_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail() -> None:
        raise OperationalError("SELECT 1", {}, Exception("secret-host"))

    monkeypatch.setattr(cli, "get_engine", fail)

    assert cli.main(["reevaluate"]) == 2
    err = capsys.readouterr().err
    assert "database" in err
    assert "secret-host" not in err
