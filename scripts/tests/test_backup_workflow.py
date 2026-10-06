"""Guards the security invariants of .github/workflows/backup-production.yml (ADR-021).
Text-based, standard library only:  python -m unittest discover -s scripts/tests
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = (ROOT / ".github/workflows/backup-production.yml").read_text(encoding="utf-8")
SCRIPT = (ROOT / "scripts/backup_db.sh").read_text(encoding="utf-8")
CODE = "\n".join(line for line in WF.splitlines() if not line.lstrip().startswith("#"))


class BackupWorkflowInvariants(unittest.TestCase):
    def test_actions_pinned_to_full_sha(self) -> None:
        uses = re.findall(r"uses:\s*(\S+)", CODE)
        self.assertTrue(uses)
        for ref in uses:
            self.assertRegex(ref, r"@[0-9a-f]{40}$", ref)

    def test_triggers_are_schedule_and_dispatch_only(self) -> None:
        for forbidden in ("pull_request", "pull_request_target", "push:"):
            self.assertNotIn(forbidden, CODE)
        self.assertIn("schedule:", CODE)
        self.assertIn("workflow_dispatch:", CODE)

    def test_main_only_production_environment_read_only(self) -> None:
        self.assertIn("github.ref == 'refs/heads/main'", CODE)
        self.assertIn("github.repository == 'dude297/internship-finder'", CODE)
        self.assertIn("environment: production", CODE)
        self.assertIn("contents: read", CODE)
        self.assertIn("persist-credentials: false", CODE)

    def test_secret_is_step_scoped_only(self) -> None:
        self.assertNotIn("secrets.", CODE.split("jobs:")[0])
        self.assertIsNone(
            re.search(r"^    env:", CODE, re.MULTILINE)
        )  # no job-level env
        self.assertEqual(
            CODE.count("secrets."), 2
        )  # the check step and the dump step, nowhere else

    def test_no_xtrace_and_pipefail(self) -> None:
        for text in (CODE, SCRIPT):
            self.assertNotRegex(text, r"set\s+-\w*x")
            self.assertNotIn("xtrace", text)
        self.assertIn("set -euo pipefail", SCRIPT)

    def test_retention_checksum_and_no_decryption_key(self) -> None:
        self.assertRegex(CODE, r"retention-days:\s*\d+")
        self.assertIn("sha256sum -c", CODE)
        self.assertNotIn("age -d", CODE)
        self.assertNotIn("AGE-SECRET-KEY", WF + SCRIPT)
        self.assertNotIn("secrets.BACKUP", CODE)

    def test_dump_streams_into_age(self) -> None:
        self.assertRegex(SCRIPT, r"--format=custom[^\n]*\\\n\s*\| \$\{AGE:-age\} -r")


if __name__ == "__main__":
    unittest.main()
