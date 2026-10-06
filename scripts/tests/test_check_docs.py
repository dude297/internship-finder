"""Tests for scripts/check_docs.py. Standard library only; synthetic repositories in temp dirs.

    python -m unittest discover -s scripts/tests
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_docs as cd  # noqa: E402

SHA = "203a56206836b9848cb898ec082eb78e771b92d7"
STATUS = {
    "production": {
        "milestone": "8.1",
        "main_sha": SHA,
        "schema_revision": "b7e3d9f1a2c4",
        "released_at": "2026-10-05",
        "release_record": "docs/releases/2026-10-05-m8-1.md",
    },
    "development": {"milestone": None, "branch": None},
}
RESEARCH_HEADER = (
    "# R\n\n> **Research only (non-normative).** Date: 2026-10-05. Last verified: 2026-10-05.\n"
    "> Used by / superseded by: not yet acted on.\n"
)


class Repo:
    """A minimal valid repository that passes every check."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        block = cd.render_status(STATUS)  # type: ignore[arg-type]
        for doc in cd.CANONICAL_DOCS:
            text = f"# {doc}\n\n## Section\n"
            if doc in cd.STATUS_BLOCKS:
                text += "\n" + block + "\n"
            self.write(doc, text)
        self.write(cd.STATUS_FILE, json.dumps(STATUS))
        self.write("docs/releases/2026-10-05-m8-1.md", "# Release\n")
        self.write(f"{cd.MIGRATIONS}/b7e3d9f1a2c4_example.py", "")
        self.write("docs/research/r.md", RESEARCH_HEADER)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def errors(self) -> list[str]:
        return cd.run(self.root)

    def close(self) -> None:
        self._tmp.cleanup()


class RepositoryChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Repo()
        self.addCleanup(self.repo.close)

    def test_valid_repository_passes(self) -> None:
        self.assertEqual(self.repo.errors(), [])

    def test_missing_canonical_document_fails(self) -> None:
        (self.repo.root / "docs/scoring.md").unlink()
        self.assertIn("missing canonical document: docs/scoring.md", self.repo.errors())

    def test_broken_link_fails(self) -> None:
        self.repo.write("docs/architecture.md", "# A\n\nSee [x](nope.md).\n")
        self.assertTrue(any("broken link nope.md" in e for e in self.repo.errors()))

    def test_missing_anchor_fails_and_real_anchor_passes(self) -> None:
        self.repo.write("docs/sources.md", "# S\n\n## Source authority (Milestone 7)\n")
        self.repo.write("docs/architecture.md", "# A\n\n[ok](sources.md#source-authority-milestone-7)\n")
        self.assertEqual(self.repo.errors(), [])
        self.repo.write("docs/architecture.md", "# A\n\n[bad](sources.md#source-authority)\n")
        self.assertTrue(any("missing anchor #source-authority" in e for e in self.repo.errors()))

    def test_links_in_code_are_ignored(self) -> None:
        self.repo.write(
            "docs/architecture.md", "# A\n\n`[x](nope.md)`\n\n```\n[y](nope.md)\n```\n"
        )
        self.assertEqual(self.repo.errors(), [])

    def test_external_links_are_not_fetched(self) -> None:
        self.repo.write("docs/architecture.md", "# A\n\n[x](https://example.invalid/a#b)\n")
        self.assertEqual(self.repo.errors(), [])

    def test_duplicate_protected_heading_fails(self) -> None:
        self.repo.write("docs/development.md", "# D\n\n## Workflow\n\nx\n\n## Workflow\n")
        self.assertTrue(any("duplicate heading 'Workflow'" in e for e in self.repo.errors()))

    def test_duplicate_h3_is_allowed(self) -> None:
        self.repo.write("docs/development.md", "# D\n\n## A\n### Notes\n## B\n### Notes\n")
        self.assertEqual(self.repo.errors(), [])

    def test_generated_status_drift_fails_and_write_fixes_it(self) -> None:
        text = (self.repo.root / "README.md").read_text(encoding="utf-8")
        self.repo.write("README.md", text.replace("Milestone 8.1", "Milestone 8"))
        self.assertTrue(any("README.md: generated status block" in e for e in self.repo.errors()))
        cd.run(self.repo.root, write=True)
        self.assertEqual(self.repo.errors(), [])

    def test_missing_status_markers_fail(self) -> None:
        self.repo.write("PROJECT_STATE.md", "# P\n")
        self.assertIn("PROJECT_STATE.md: generated status block markers missing", self.repo.errors())

    def test_invalid_status_schema_fails(self) -> None:
        bad = json.loads(json.dumps(STATUS))
        bad["production"]["main_sha"] = "203a562"
        bad["production"]["schema_revision"] = "000000000000"
        bad["development"] = {"milestone": "9", "branch": None}
        self.repo.write(cd.STATUS_FILE, json.dumps(bad))
        errors = " ".join(self.repo.errors())
        self.assertIn("full 40-character SHA", errors)
        self.assertIn("has no migration file", errors)
        self.assertIn("set together", errors)

    def test_status_with_extra_field_fails(self) -> None:
        bad = json.loads(json.dumps(STATUS))
        bad["production"]["database_url"] = "postgresql://user:secret@host/db"
        self.repo.write(cd.STATUS_FILE, json.dumps(bad))
        self.assertTrue(any("production must have exactly" in e for e in self.repo.errors()))

    def test_research_header_required(self) -> None:
        self.repo.write("docs/research/r.md", "# R\n\nFindings.\n")
        errors = self.repo.errors()
        self.assertTrue(any("research-only header" in e for e in errors))


class PathGuards(unittest.TestCase):
    def test_migration_without_data_model_fails(self) -> None:
        errors = cd.path_guard_failures(["backend/alembic/versions/x_add.py"], set(), None)
        self.assertEqual(len(errors), 1)
        self.assertIn("[migration]", errors[0])

    def test_scoring_without_scoring_doc_fails(self) -> None:
        errors = cd.path_guard_failures(["backend/app/opportunities/scoring/engine.py"], set(), None)
        self.assertIn("docs/scoring.md", errors[0])

    def test_adapter_with_sources_doc_passes(self) -> None:
        changed = ["backend/app/ingestion/adapters/lever.py", "docs/sources.md"]
        self.assertEqual(cd.path_guard_failures(changed, set(), None), [])

    def test_tests_and_docs_only_changes_pass(self) -> None:
        changed = ["backend/tests/test_scoring.py", "docs/architecture.md", "frontend/src/App.tsx"]
        self.assertEqual(cd.path_guard_failures(changed, set(), None), [])

    def test_eligibility_and_requirements_need_eligibility_doc(self) -> None:
        for path in (
            "backend/app/opportunities/eligibility/rules.py",
            "backend/app/opportunities/requirements/extractor.py",
        ):
            self.assertIn("docs/eligibility.md", cd.path_guard_failures([path], set(), None)[0])

    def test_sync_workflow_needs_operations_doc(self) -> None:
        errors = cd.path_guard_failures([".github/workflows/sync-production.yml"], set(), None)
        self.assertIn("docs/operations.md", errors[0])

    def test_waiver_trailer_waives_only_its_rule(self) -> None:
        changed = ["backend/app/opportunities/scoring/text.py", "backend/app/models/profile.py"]
        waived = cd.waivers("refactor\n\nDocs-Impact-Waiver: scoring: rename private helper only\n")
        errors = cd.path_guard_failures(changed, waived, None)
        self.assertEqual(len(errors), 1)
        self.assertIn("[models]", errors[0])

    def test_waiver_without_reason_is_ignored(self) -> None:
        self.assertEqual(cd.waivers("Docs-Impact-Waiver: scoring: x\n"), set())
        self.assertEqual(cd.waivers("Docs-Impact-Waiver: nonsense: a long enough reason\n"), set())

    def test_feature_branch_needs_project_state_and_changelog(self) -> None:
        errors = cd.path_guard_failures(["frontend/src/App.tsx"], set(), "feature/m9-x")
        self.assertIn("PROJECT_STATE.md, CHANGELOG.md", errors[0])
        ok = cd.path_guard_failures(
            ["frontend/src/App.tsx", "PROJECT_STATE.md", "CHANGELOG.md", "docs/status.json"], set(), "feature/m9-x"
        )
        self.assertEqual(ok, [])
        self.assertEqual(cd.path_guard_failures(["frontend/src/App.tsx"], set(), "chore/x"), [])


class GitRange(unittest.TestCase):
    """check_paths against a real (temporary) git history."""

    def test_check_paths_reads_the_range_and_trailers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args: str) -> None:
                subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

            git("init", "-q", "-b", "main")
            git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "test")
            (root / "a.txt").write_text("a")
            git("add", ".")
            git("commit", "-q", "-m", "base")
            scoring = root / "backend/app/opportunities/scoring"
            scoring.mkdir(parents=True)
            (scoring / "engine.py").write_text("x = 1\n")
            git("add", ".")
            git("commit", "-q", "-m", "change scoring")
            self.assertTrue(cd.check_paths(root, "main~1", None))
            git("commit", "-q", "--allow-empty", "-m", "x\n\nDocs-Impact-Waiver: scoring: constant rename only")
            self.assertEqual(cd.check_paths(root, "main~2", None), [])


class ReviewRegressions(unittest.TestCase):
    """Stale-documentation paths found by the hostile review."""

    def test_behavior_code_outside_original_prefixes_needs_its_doc(self) -> None:
        expected = {
            "backend/app/core/config.py": "docs/deployment.md",
            "backend/app/cli.py": "docs/operations.md",
            "backend/app/enums.py": "docs/data-model.md",
            "backend/app/services/freshness.py": "docs/operations.md",
            "backend/app/services/requirement_candidates.py": "docs/eligibility.md",
            "backend/app/services/discovery.py": "docs/sources.md",
            "backend/data/program_registry.json": "docs/sources.md",
            ".github/workflows/ci.yml": "docs/development.md",
        }
        for path, doc in expected.items():
            self.assertIn(doc, cd.path_guard_failures([path], set(), None)[0], path)

    def test_feature_branch_must_also_update_status_json(self) -> None:
        errors = cd.path_guard_failures(["PROJECT_STATE.md", "CHANGELOG.md"], set(), "feature/m9")
        self.assertIn("docs/status.json", errors[0])

    def test_reference_style_link_definitions_are_checked(self) -> None:
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write("docs/architecture.md", "# A\n\n[x][r]\n\n[r]: nope.md\n")
        self.assertTrue(any("broken link nope.md" in e for e in repo.errors()))

    def test_link_with_wrong_case_fails_even_on_case_insensitive_filesystems(self) -> None:
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write("docs/architecture.md", "# A\n\n[x](Scoring.md)\n")
        self.assertTrue(any("broken link Scoring.md" in e for e in repo.errors()))

    def test_production_status_change_needs_release_record(self) -> None:
        old = {"production": {"milestone": "8.1"}}
        new = {"production": {"milestone": "9"}}
        self.assertTrue(cd.status_release_failures(old, new, ["docs/status.json"]))
        self.assertEqual(cd.status_release_failures(old, new, ["docs/releases/2026-11-01-m9.md"]), [])
        self.assertEqual(cd.status_release_failures(old, old, ["docs/status.json"]), [])

    def test_release_record_rewrite_fails_but_append_passes(self) -> None:
        self.assertEqual(cd.release_rewrite_failures("5\t0\tdocs/releases/a.md\n"), [])
        self.assertTrue(cd.release_rewrite_failures("1\t1\tdocs/releases/a.md\n"))


class ReviewGitRegressions(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "test")
        self.write("docs/data-model.md", "# D\n\nx\n")
        self.write("backend/alembic/versions/a_1.py", "x = 1\n" * 20)
        self.commit("base")

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def test_whitespace_only_doc_edit_does_not_satisfy_a_rule(self) -> None:
        self.write("backend/alembic/versions/b_2.py", "y = 2\n")
        self.write("docs/data-model.md", "# D\n\nx   \n\n")
        self.commit("migration")
        self.assertTrue(any("[migration]" in e for e in cd.check_paths(self.root, "main~1", None)))
        self.write("docs/data-model.md", "# D\n\nx\n\nNew table.\n")
        self.commit("real doc edit")
        self.assertEqual(cd.check_paths(self.root, "main~2", None), [])

    def test_renamed_migration_still_triggers_its_rule(self) -> None:
        self.git("mv", "backend/alembic/versions/a_1.py", "backend/alembic/other_a_1.py")
        self.commit("move")
        self.assertTrue(any("[migration]" in e for e in cd.check_paths(self.root, "main~1", None)))

    def test_unreachable_base_is_reported_not_a_traceback(self) -> None:
        errors = cd.check_paths(self.root, "deadbeef" * 5, None)
        self.assertTrue(errors and "cannot diff against base" in errors[0])


class Slugs(unittest.TestCase):
    def test_github_slugs(self) -> None:
        self.assertEqual(cd.slug("Milestone 8.1 release (2026-10-05)"), "milestone-81-release-2026-10-05")
        self.assertEqual(cd.slug("### `opportunity_evaluations`".lstrip("# ")), "opportunity_evaluations")
        self.assertEqual(cd.slug("Change → canonical document"), "change--canonical-document")
        self.assertEqual(cd.anchors("# A\n## B\n## B\n"), {"a", "b", "b-1"})


if __name__ == "__main__":
    unittest.main()
