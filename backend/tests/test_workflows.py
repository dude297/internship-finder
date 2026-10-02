"""Structural checks on the scheduled-sync workflow (ADR-012 §10): never give a fork PR the
production secret, never leak it in a job/workflow env, never dump the environment. No YAML
parser is added for this (PyYAML isn't a project dependency); these are text-level checks against
a workflow file whose structure this suite also pins down."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "sync-production.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_file_exists() -> None:
    assert WORKFLOW.is_file()


def test_only_schedule_and_dispatch_trigger_it() -> None:
    text = _text()
    on_block = text.split("\non:", 1)[1].split("\npermissions:", 1)[0]
    assert "schedule" in on_block
    assert "workflow_dispatch" in on_block
    for forbidden in ("pull_request_target", "pull_request", "push:"):
        assert forbidden not in on_block


def test_two_daily_schedules_with_timezone() -> None:
    text = _text()
    crons = re.findall(r'cron:\s*"([^"]+)"', text)
    assert len(crons) == 2
    timezones = re.findall(r'timezone:\s*"([^"]+)"', text)
    assert timezones == ["America/Los_Angeles", "America/Los_Angeles"]


def test_permissions_are_read_only_contents() -> None:
    text = _text()
    permissions_block = text.split("\npermissions:", 1)[1].split("\n\n", 1)[0]
    assert "contents: read" in permissions_block
    assert "write" not in permissions_block


def test_timeout_is_present_and_bounded() -> None:
    match = re.search(r"timeout-minutes:\s*(\d+)", _text())
    assert match is not None
    assert 0 < int(match.group(1)) <= 30


def test_concurrency_group_never_cancels_in_progress() -> None:
    text = _text()
    concurrency_block = text.split("concurrency:", 1)[1].split("\n\n", 1)[0]
    assert "group: production-source-sync" in concurrency_block
    assert "cancel-in-progress: false" in concurrency_block


def test_repository_and_branch_guard() -> None:
    text = _text()
    assert "github.repository == 'dude297/internship-finder'" in text
    assert "github.ref == 'refs/heads/main'" in text


def test_secret_is_scoped_to_one_step_env_not_job_or_workflow_env() -> None:
    text = _text()
    lines = text.splitlines()
    secret_lines = [
        (n, line) for n, line in enumerate(lines) if "secrets.PRODUCTION_DATABASE_URL" in line
    ]
    assert len(secret_lines) == 2  # the empty-check step and the sync step, both narrowly scoped
    for lineno, line in secret_lines:
        # Walk upward to the nearest `env:` line and confirm it's indented well past the job's
        # own top-level keys (`jobs:`/`steps:` sit at 2-4 spaces here), i.e. it's a step's own
        # env, not a job- or workflow-level one.
        env_lines_above = [above for above in reversed(lines[:lineno]) if above.strip() == "env:"]
        assert env_lines_above, f"no enclosing env: for {line!r}"
        nearest = env_lines_above[0]
        indent = len(nearest) - len(nearest.lstrip(" "))
        assert indent >= 8, f"env: block for the secret is not step-scoped: {nearest!r}"


def test_no_debug_dumping_or_artifact_upload() -> None:
    text = _text()
    for forbidden in ("set -x", "printenv", "upload-artifact"):
        assert forbidden not in text
    # No shell line that runs a bare `env` dump command (a YAML `env:` key is fine).
    for line in text.splitlines():
        code = line.split("#", 1)[0].strip()
        assert not re.fullmatch(r"env(\s*(\||;|&&).*)?", code)


def test_persist_credentials_disabled_on_checkout() -> None:
    assert "persist-credentials: false" in _text()


def test_actions_are_pinned_to_commit_shas() -> None:
    """The job holds the production database secret: a moved tag must not change what runs."""
    uses = re.findall(r"uses:\s*(\S+)", _text())
    assert uses
    for action in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action), action


def test_scheduled_run_checks_the_schema_first() -> None:
    assert "sync-sources --scheduled" in _text()


def test_fails_fast_without_echoing_when_secret_is_empty() -> None:
    text = _text()
    assert "DATABASE_URL" in text
    assert '-z "$DATABASE_URL"' in text
    assert 'echo "$DATABASE_URL"' not in text


def test_ci_workflow_is_unaffected() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "sync-production" not in text
    assert "PRODUCTION_DATABASE_URL" not in text
