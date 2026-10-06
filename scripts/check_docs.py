"""Documentation guard (docs/README.md "Enforcement"). Standard library only, no network.

    python scripts/check_docs.py                      # repository checks
    python scripts/check_docs.py --base origin/main   # + changed-path guards for a PR/push range
    python scripts/check_docs.py --write-status       # regenerate the status blocks from docs/status.json

Repository checks: canonical documents exist; docs/status.json is valid and its schema revision
exists; the generated status blocks in README.md and PROJECT_STATE.md match it; internal Markdown
links and anchors resolve; no duplicate H1/H2 heading inside a canonical document; every research
document carries the research-only header.

Changed-path guards (with --base): high-confidence code paths must change together with their
canonical document, and `feature/` branches must update PROJECT_STATE.md and CHANGELOG.md. A
genuinely docs-neutral change (pure refactor, formatting) is waived only by a commit trailer in the
range, which stays in history for review:

    Docs-Impact-Waiver: <rule>: <reason, at least 10 characters>
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANONICAL_DOCS = (
    "README.md",
    "PROJECT_STATE.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "ENGINEERING_GUIDELINES.md",
    "docs/README.md",
    "docs/architecture.md",
    "docs/data-model.md",
    "docs/development.md",
    "docs/eligibility.md",
    "docs/scoring.md",
    "docs/sources.md",
    "docs/operations.md",
    "docs/deployment.md",
    "docs/status.json",
)
STATUS_FILE = "docs/status.json"
STATUS_BLOCKS = ("README.md", "PROJECT_STATE.md")
BEGIN = "<!-- BEGIN GENERATED STATUS (scripts/check_docs.py --write-status) -->"
END = "<!-- END GENERATED STATUS -->"
MIGRATIONS = "backend/alembic/versions"
RESEARCH_DIR = "docs/research"
RESEARCH_MARKER = "**Research only (non-normative).**"
SKIP_DIRS = {".git", "node_modules", ".venv", ".claude", "dist", "test-results", "__pycache__"}

# Code path prefix -> canonical document that must change with it. Only high-confidence pairs: a
# change under the prefix almost always changes the behavior that document describes.
@dataclass(frozen=True)
class Rule:
    name: str
    prefixes: tuple[str, ...]
    doc: str


RULES = (
    Rule("migration", (f"{MIGRATIONS}/",), "docs/data-model.md"),
    Rule("models", ("backend/app/models/", "backend/app/enums.py"), "docs/data-model.md"),
    Rule(
        "eligibility",
        (
            "backend/app/opportunities/eligibility/",
            "backend/app/opportunities/requirements/",
            "backend/app/services/requirement_candidates.py",
            "backend/app/services/requirement_review.py",
        ),
        "docs/eligibility.md",
    ),
    Rule("scoring", ("backend/app/opportunities/scoring/",), "docs/scoring.md"),
    Rule(
        "ingestion",
        (
            "backend/app/ingestion/",
            "backend/data/direct_source_catalog.json",
            "backend/data/program_registry.json",
            "backend/app/services/direct_catalog.py",
            "backend/app/services/discovery.py",
            "backend/app/services/source_discovery.py",
            "backend/app/services/sources.py",
        ),
        "docs/sources.md",
    ),
    Rule(
        "scheduling",
        (
            ".github/workflows/sync-production.yml",
            "backend/app/services/source_health.py",
            "backend/app/services/freshness.py",
            "backend/app/cli.py",
        ),
        "docs/operations.md",
    ),
    Rule("config", ("backend/app/core/config.py",), "docs/deployment.md"),
    Rule("ci", (".github/workflows/ci.yml",), "docs/development.md"),
    Rule("hosting", ("frontend/vercel.json",), "docs/deployment.md"),
)
RULE_NAMES = {rule.name for rule in RULES} | {"milestone"}
WAIVER = re.compile(r"^Docs-Impact-Waiver:\s*([a-z-]+)\s*:\s*(\S.{9,})$", re.MULTILINE)
MILESTONE_DOCS = ("PROJECT_STATE.md", "CHANGELOG.md", STATUS_FILE)
RELEASES_DIR = "docs/releases/"

SHA = re.compile(r"[0-9a-f]{40}")
REVISION = re.compile(r"[0-9a-f]{12}")
MILESTONE = re.compile(r"\d+(\.\d+)?")


# --- Markdown helpers -----------------------------------------------------------------------------

FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
REFDEF = re.compile(r"^ {0,3}\[[^\]]+\]:\s*<?([^\s>]+)")  # [ref]: target
LINK = re.compile(r"(?<!!)\[(?:[^\]\[]|\[[^\]]*\])*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE = re.compile(r"`[^`]*`")


def prose_lines(text: str, keep_code: bool = False) -> Iterable[tuple[int, str]]:
    """(line number, line) outside fenced code blocks; inline code removed unless keep_code."""
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield number, line if keep_code else INLINE_CODE.sub("", line)


def headings(text: str) -> list[tuple[int, int, str]]:
    """(line, level, text) of ATX headings outside code blocks."""
    found: list[tuple[int, int, str]] = []
    for number, line in prose_lines(text, keep_code=True):
        match = HEADING.match(line)
        if match:
            found.append((number, len(match.group(1)), match.group(2)))
    return found


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, drop punctuation, spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # links keep their text
    text = re.sub(r"[*`]", "", text).strip().lower()  # GitHub keeps underscores
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(text: str) -> set[str]:
    seen: dict[str, int] = {}
    result: set[str] = set()
    for _, _, heading in headings(text):
        base = slug(heading)
        count = seen.get(base, 0)
        result.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return result


def markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for directory, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        files.extend(Path(directory) / n for n in names if n.endswith(".md"))
    return sorted(files)


# --- repository checks ------------------------------------------------------------------------------


def check_canonical(root: Path) -> list[str]:
    return [f"missing canonical document: {doc}" for doc in CANONICAL_DOCS if not (root / doc).is_file()]


def load_status(root: Path) -> tuple[dict[str, object] | None, list[str]]:
    path = root / STATUS_FILE
    if not path.is_file():
        return None, []
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return None, [f"{STATUS_FILE}: invalid JSON ({error})"]
    return status, validate_status(status, root)


def validate_status(status: object, root: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(status, dict) or set(status) != {"production", "development"}:
        return [f"{STATUS_FILE}: top level must be exactly {{production, development}}"]
    production, development = status["production"], status["development"]
    keys = {"milestone", "main_sha", "schema_revision", "released_at", "release_record"}
    if not isinstance(production, dict) or set(production) != keys:
        errors.append(f"{STATUS_FILE}: production must have exactly {sorted(keys)}")
    else:
        if not (isinstance(production["milestone"], str) and MILESTONE.fullmatch(production["milestone"])):
            errors.append(f"{STATUS_FILE}: production.milestone must look like '8.1'")
        if not (isinstance(production["main_sha"], str) and SHA.fullmatch(production["main_sha"])):
            errors.append(f"{STATUS_FILE}: production.main_sha must be a full 40-character SHA")
        revision = production["schema_revision"]
        if not (isinstance(revision, str) and REVISION.fullmatch(revision)):
            errors.append(f"{STATUS_FILE}: production.schema_revision must be a 12-hex revision")
        elif not list((root / MIGRATIONS).glob(f"{revision}_*.py")):
            errors.append(f"{STATUS_FILE}: schema_revision {revision} has no migration file")
        try:
            date.fromisoformat(str(production["released_at"]))
        except ValueError:
            errors.append(f"{STATUS_FILE}: production.released_at must be YYYY-MM-DD")
        record = production["release_record"]
        if not (isinstance(record, str) and record.startswith("docs/releases/") and (root / record).is_file()):
            errors.append(f"{STATUS_FILE}: production.release_record must be an existing docs/releases/ file")
    if not isinstance(development, dict) or set(development) != {"milestone", "branch"}:
        errors.append(f"{STATUS_FILE}: development must have exactly ['branch', 'milestone']")
    else:
        milestone, branch = development["milestone"], development["branch"]
        if milestone is not None and not (isinstance(milestone, str) and MILESTONE.fullmatch(milestone)):
            errors.append(f"{STATUS_FILE}: development.milestone must be null or look like '9'")
        if branch is not None and not isinstance(branch, str):
            errors.append(f"{STATUS_FILE}: development.branch must be null or a branch name")
        if (milestone is None) != (branch is None):
            errors.append(f"{STATUS_FILE}: development.milestone and branch are set together")
    return errors


def check_sha_in_history(root: Path, status: dict[str, object] | None) -> list[str]:
    """In a git checkout with history, production.main_sha must be a real commit."""
    production = status.get("production") if isinstance(status, dict) else None
    sha = production.get("main_sha") if isinstance(production, dict) else None
    if not (root / ".git").exists() or not isinstance(sha, str) or not SHA.fullmatch(sha):
        return []
    found = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=root, capture_output=True)
    return [] if found.returncode == 0 else [f"{STATUS_FILE}: production.main_sha {sha[:7]} is not a commit in this repository"]


def render_status(status: dict[str, dict[str, str | None]]) -> str:
    production, development = status["production"], status["development"]
    sha = str(production["main_sha"])
    if development["milestone"]:
        current_development = f"Milestone {development['milestone']} on `{development['branch']}`"
    else:
        current_development = "none"
    return "\n".join(
        (
            BEGIN,
            "| | |",
            "|---|---|",
            f"| **Current Production** | Milestone {production['milestone']}, released "
            f"{production['released_at']} ([release record]({production['release_record']})) |",
            f"| Production `main` | `{sha[:7]}` |",
            f"| Production schema | `{production['schema_revision']}` |",
            f"| **Current Development** | {current_development} |",
            END,
        )
    )


def relink(block: str, from_doc: str) -> str:
    """Status block links are written repository-relative; adjust them for the document's
    directory (all status documents live at the root today)."""
    depth = from_doc.count("/")
    return block.replace("](docs/", "](" + "../" * depth + "docs/") if depth else block


def check_status_blocks(root: Path, status: dict[str, object] | None, write: bool) -> list[str]:
    errors: list[str] = []
    if status is None:
        return errors
    expected = render_status(status)  # type: ignore[arg-type]
    for doc in STATUS_BLOCKS:
        path = root / doc
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        start, end = text.find(BEGIN), text.find(END)
        if start < 0 or end < start:
            errors.append(f"{doc}: generated status block markers missing")
            continue
        current = text[start : end + len(END)]
        wanted = relink(expected, doc)
        if current != wanted:
            if write:
                path.write_text(text[:start] + wanted + text[end + len(END) :], encoding="utf-8", newline="\n")
            else:
                errors.append(f"{doc}: generated status block is out of date (run --write-status)")
    return errors


def exists_exact_case(path: Path, root: Path) -> bool:
    """exists(), but case-sensitive like Linux CI (Windows/macOS filesystems are not)."""
    if not path.exists():
        return False
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    current = root
    for part in parts:
        if part not in os.listdir(current):
            return False
        current = current / part
    return True


def check_links(root: Path) -> list[str]:
    errors: list[str] = []
    cache: dict[Path, set[str]] = {}
    for path in markdown_files(root):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        for number, line in prose_lines(text):
            for target in LINK.findall(line) + REFDEF.findall(line):
                if re.match(r"[a-z]+:", target) or target.startswith("//"):
                    continue  # external (http, https, mailto)
                file_part, _, anchor = target.partition("#")
                resolved = path if not file_part else Path(os.path.normpath(path.parent / file_part))
                if not exists_exact_case(resolved, root):
                    errors.append(f"{rel}:{number}: broken link {target}")
                    continue
                if anchor and resolved.suffix == ".md":
                    if resolved not in cache:
                        cache[resolved] = anchors(resolved.read_text(encoding="utf-8"))
                    if anchor.lower() not in cache[resolved]:
                        errors.append(f"{rel}:{number}: missing anchor #{anchor} in {file_part or rel}")
    return errors


def check_duplicate_headings(root: Path) -> list[str]:
    errors: list[str] = []
    for doc in CANONICAL_DOCS:
        path = root / doc
        if not path.is_file() or path.suffix != ".md":
            continue
        seen: dict[str, int] = {}
        for number, level, heading in headings(path.read_text(encoding="utf-8")):
            if level > 2:
                continue
            key = heading.strip().lower()
            if key in seen:
                errors.append(f"{doc}:{number}: duplicate heading '{heading}' (first at line {seen[key]})")
            else:
                seen[key] = number
    return errors


def check_research(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted((root / RESEARCH_DIR).glob("*.md")):
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:8])
        rel = path.relative_to(root).as_posix()
        if RESEARCH_MARKER not in head or not re.search(r"Date: \d{4}-\d{2}-\d{2}", head):
            errors.append(f"{rel}: missing the research-only header (status and Date) near the top")
        if "Used by / superseded by:" not in head:
            errors.append(f"{rel}: missing 'Used by / superseded by:' in the research header")
    return errors


# --- changed-path guards ------------------------------------------------------------------------------


def waivers(messages: str) -> set[str]:
    return {match.group(1) for match in WAIVER.finditer(messages) if match.group(1) in RULE_NAMES}


def path_guard_failures(changed: Sequence[str], waived: set[str], branch: str | None) -> list[str]:
    """Pure: which rules a change set violates."""
    changed_set = set(changed)
    errors: list[str] = []
    for rule in RULES:
        hits = sorted(p for p in changed if p.startswith(rule.prefixes))
        if hits and rule.doc not in changed_set and rule.name not in waived:
            errors.append(
                f"[{rule.name}] {', '.join(hits[:3])}{' …' if len(hits) > 3 else ''} changed but "
                f"{rule.doc} didn't (update it, or add a 'Docs-Impact-Waiver: {rule.name}: <reason>' "
                "commit trailer if behavior is truly unchanged)"
            )
    if branch and branch.startswith("feature/") and "milestone" not in waived:
        missing = [doc for doc in MILESTONE_DOCS if doc not in changed_set]
        if missing:
            errors.append(f"[milestone] feature branch {branch} must update {', '.join(missing)}")
    return errors


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def status_release_failures(old: object, new: object, changed: Sequence[str]) -> list[str]:
    """Production status may only change together with a release record (a new file, or a dated
    note appended to an existing one)."""
    if not (isinstance(old, dict) and isinstance(new, dict)) or old.get("production") == new.get("production"):
        return []
    if any(p.startswith(RELEASES_DIR) for p in changed):
        return []
    return [f"[release] {STATUS_FILE} production changed without a docs/releases/ record in the same range"]


def release_rewrite_failures(numstat: str) -> list[str]:
    """Release records are immutable: only additions (new files, appended notes) are allowed."""
    errors = []
    for line in numstat.splitlines():
        _, deleted, path = line.split("\t", 2)
        if deleted != "0":
            errors.append(f"[release] {path}: release records are immutable (append a dated note instead)")
    return errors


def check_paths(root: Path, base: str, branch: str | None) -> list[str]:
    span = f"{base}...HEAD"
    try:
        # --no-renames: a moved file is delete + add, so the old path still triggers its rule
        changed = [p for p in git(root, "diff", "--name-only", "--no-renames", span).splitlines() if p]
        messages = git(root, "log", "--format=%B", f"{base}..HEAD")
        # a whitespace-only edit does not count as updating a document
        for doc in [p for p in changed if p.endswith(".md")]:
            if not git(root, "diff", "-w", "--ignore-blank-lines", "--numstat", span, "--", doc).strip():
                changed.remove(doc)
        releases = git(root, "diff", "--numstat", "--no-renames", span, "--", RELEASES_DIR)
    except subprocess.CalledProcessError as error:
        return [f"cannot diff against base '{base}' ({(error.stderr or '').strip()[:200]}); is the history fetched?"]
    errors = path_guard_failures(changed, waivers(messages), branch) + release_rewrite_failures(releases)
    if STATUS_FILE in changed:
        try:
            old = json.loads(git(root, "show", f"{base}:{STATUS_FILE}"))
            new = json.loads((root / STATUS_FILE).read_text(encoding="utf-8"))
        except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
            old = new = None  # invalid JSON is reported by the repository checks
        errors += status_release_failures(old, new, changed)
    return errors


def run(root: Path, base: str | None = None, branch: str | None = None, write: bool = False) -> list[str]:
    status, errors = load_status(root)
    errors = check_canonical(root) + errors
    errors += check_sha_in_history(root, status)
    errors += check_status_blocks(root, status, write)
    errors += check_links(root)
    errors += check_duplicate_headings(root)
    errors += check_research(root)
    if base:
        errors += check_paths(root, base, branch)
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="git ref to diff against for the changed-path guards")
    parser.add_argument("--branch", default=os.environ.get("GITHUB_HEAD_REF") or None)
    parser.add_argument("--write-status", action="store_true")
    args = parser.parse_args(argv)
    errors = run(ROOT, args.base, args.branch, args.write_status)
    for error in errors:
        print(f"docs: {error}")
    print(f"docs check: {'FAIL' if errors else 'OK'} ({len(errors)} problem(s))")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
