"""Guards the security invariants of .github/workflows/backup-production.yml (ADR-021).
Text-based, standard library only:  python -m unittest discover -s scripts/tests
"""

import os
import re
import shutil
import subprocess
import tempfile
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

    def test_tool_stderr_withheld_and_hardening(self) -> None:
        self.assertIn('2>>"$errfile"', SCRIPT)
        self.assertIn("::add-mask::", SCRIPT)
        self.assertIn('PGSSLMODE="${PGSSLMODE:-require}"', SCRIPT)
        self.assertIn("ulimit -c 0", SCRIPT)
        self.assertIn("select count(*) from opportunities", SCRIPT)
        self.assertIn("age1pq1", SCRIPT)

    def test_pgdg_key_file_must_hold_exactly_one_key(self) -> None:
        self.assertIn("grep -c '^pub')\" = 1", CODE)

    def test_dump_streams_into_age(self) -> None:
        self.assertRegex(SCRIPT, r"--format=custom[^\n]*\\\n\s*\| \$\{AGE:-age\} -r")


@unittest.skipIf(os.name == "nt" or not shutil.which("bash"), "needs a POSIX bash (CI runs Linux)")
class BackupScriptRun(unittest.TestCase):
    def test_password_reaches_libpq_by_env_not_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp, "argv.log")
            # Stubs record argv and PGPASSWORD; the fake dump is large enough to pass the size check.
            stub = Path(tmp, "stub.sh")
            stub.write_text(
                "#!/usr/bin/env bash\n"
                f'echo "$0|$*|$PGPASSWORD" >> "{log.as_posix()}"\n'
                'case "$0" in *psql) echo 42;; *dump) head -c 9000 /dev/zero;;'
                ' *age) cat >/dev/null; printf "age-encryption.org/v1"; head -c 9000 /dev/zero;; esac\n',
                encoding="utf-8",
            )
            for name in ("psql", "dump", "age"):
                shutil.copy(stub, Path(tmp, name))
            env = {
                **os.environ,
                "DATABASE_URL": "postgresql+psycopg://role:s3cr%40t@ep-x-pooler.neon.tech/db",
                "BACKUP_AGE_RECIPIENT": "age1" + "q" * 58,
                "PSQL": f"bash {Path(tmp, 'psql').as_posix()}",
                "PG_DUMP": f"bash {Path(tmp, 'dump').as_posix()}",
                "AGE": f"bash {Path(tmp, 'age').as_posix()}",
            }
            env.pop("GITHUB_ACTIONS", None)
            out = Path(tmp, "b.age").as_posix()
            run = subprocess.run(
                ["bash", (ROOT / "scripts/backup_db.sh").as_posix(), out],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            lines = log.read_text(encoding="utf-8").splitlines()
            self.assertGreaterEqual(len(lines), 2)
            for line in lines:
                argv, password = line.rsplit("|", 1)
                self.assertNotIn("s3cr", argv)
                if "age" not in argv.split("|")[0]:
                    self.assertEqual(password, "s3cr@t")
                    self.assertIn("role@ep-x.neon.tech/db", argv)


if __name__ == "__main__":
    unittest.main()
