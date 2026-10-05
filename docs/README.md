# Documentation Map and Authority

Every document has one job. When two documents could say the same thing, only the one named here says it; the others link to it.

## Canonical sources

| Document | Owns | Never contains |
|---|---|---|
| [README.md](../README.md) | Public overview: what the app does, stack, quick start | Release details, current counts |
| [PROJECT_STATE.md](../PROJECT_STATE.md) | **Current** project and production truth: production vs development status, open issues, debt, next task, recent decisions | Release narration, old snapshots, milestone diaries |
| [CHANGELOG.md](../CHANGELOG.md) | Historical product changes, one entry per milestone | Runbooks, current state |
| [CLAUDE.md](../CLAUDE.md), [ENGINEERING_GUIDELINES.md](../ENGINEERING_GUIDELINES.md) | How work is done (agent contract, standards) | Product behavior |
| [architecture.md](architecture.md) | Current architecture: components, layers, flows | Planned work presented as current |
| [data-model.md](data-model.md) | Current schema, domain rules, migration list | Release logs |
| [eligibility.md](eligibility.md) | Current eligibility and requirement semantics | |
| [scoring.md](scoring.md) | Current fit-scoring semantics | |
| [sources.md](sources.md) | Current source, ingestion, authority, and catalog semantics | Production source inventories (those are release records / `GET /api/sources`) |
| [operations.md](operations.md) | Current runtime operations: sync, health, scans, activation procedure, capacity | Executed runbooks |
| [deployment.md](deployment.md) | Current topology, configuration, deploy and release procedure, smoke checks, rollback | Per-release results |
| [development.md](development.md) | Local setup, commands, tests, CI, migrations workflow | |
| [decisions/](decisions/) | Architectural decision history (ADRs) | |
| [research/](research/) | Dated, **non-normative** research | Anything treated as current behavior |
| [releases/](releases/) | **Immutable** production release records | |
| [status.json](status.json) | The machine-readable current production/development status | Secrets, URLs, volatile metrics |

**When documents disagree:** code plus accepted ADRs define implemented behavior; `docs/status.json` (and the status blocks generated from it) plus PROJECT_STATE.md define current production state. Any disagreement is drift and is fixed immediately, in the change that finds it.

## Current status

[`status.json`](status.json) holds only values that have exactly one authoritative current answer: the production milestone, the production `main` SHA, the production schema revision, the release date, the current release record, and the active development milestone/branch (or `null`). It never holds secrets, credentials, private data, or counts that change with every sync.

The status blocks at the top of README.md and PROJECT_STATE.md are generated from it (between `BEGIN/END GENERATED STATUS` markers). Edit `status.json`, then run `python scripts/check_docs.py --write-status`; never edit the blocks by hand.

## Release records

`docs/releases/<YYYY-MM-DD>-<milestone>.md`, one per production release (for example `2026-10-05-m8-1.md`): feature PR, approved head, resulting `main`, CI, migration, Render and Vercel deploys, smoke results, activation, production counts, incidents, rollback notes, known limitations. Written in the release closeout PR and **immutable** afterwards: a later correction is a dated note appended at the end, never an edit in place. Records before 2026-10-05 were moved verbatim out of PROJECT_STATE.md, deployment.md, and operations.md; [`archive-project-state-2026-10-05.md`](releases/archive-project-state-2026-10-05.md) holds the rest of PROJECT_STATE's history.

## ADRs

Accepted ADRs are immutable decisions. A changed decision is a new ADR (`Superseded by ADR-NNN` added to the old one's status line) or a dated **Amendment** section. The only in-place edits allowed are editorial link-target repairs that don't change the decision text (the docs check flags broken links).

## Research

Each file in `research/` starts with a header naming it research only, its date, when its facts were last verified, and which ADR or implementation used or superseded it. Research is input to decisions, never a description of current behavior.

## Sprint documentation contract

Documentation is part of the implementation, not follow-up work. A milestone or sprint is not complete until code, tests, the canonical documents below, PROJECT_STATE.md, CHANGELOG.md, any affected ADR, and known limitations are synchronized and the docs check is green.

Which document each kind of change must update: [ENGINEERING_GUIDELINES.md §15](../ENGINEERING_GUIDELINES.md#change--canonical-document).

Before opening a feature PR, run a **Documentation Impact Audit** and put it in the PR description:

```text
Changed behavior: <what changed>
Affected canonical docs: <from the table above>
Updated: <docs changed, and what>
Not applicable: <docs reviewed and left unchanged>
Reason: <why each unchanged doc is still accurate>
```

"Docs updated" alone is not an audit.

A milestone PR updates PROJECT_STATE.md's **Current Development** (and `docs/status.json` `development`) while **Current Production** stays the released milestone. Never merge the two.

## Release closeout contract

After a production deployment the milestone is **RELEASED — DOCS CLOSEOUT PENDING** until a small docs-only closeout PR merges with:

1. a new `docs/releases/<date>-<milestone>.md`;
2. `docs/status.json` production (and `development` cleared) and the regenerated status blocks;
3. PROJECT_STATE.md (current production, schema, open operational issues, next task);
4. CHANGELOG.md (the milestone's released line);
5. topic documents only where production behavior differs from what the feature PR documented.

Only after it merges is the milestone **COMPLETE**. The procedure is in [deployment.md](deployment.md#release-procedure).

## Enforcement

`python scripts/check_docs.py` (stdlib only; CI job `docs` on every pull request and push to `main`):

- canonical documents exist; `status.json` is valid and its schema revision has a migration file; generated status blocks match it;
- internal Markdown links and `#anchors` resolve; no duplicate H1/H2 inside a canonical document; research headers present;
- with `--base <ref>`: code paths changed without their canonical document fail (migrations/models → data-model.md; eligibility/requirements → eligibility.md; scoring → scoring.md; ingestion/catalog → sources.md; sync workflow/source health → operations.md; `vercel.json` → deployment.md), and `feature/` branches must change PROJECT_STATE.md and CHANGELOG.md.

A change that truly leaves behavior unchanged (refactor, formatting, comments) is waived per rule with a commit trailer, which stays reviewable in history:

```text
Docs-Impact-Waiver: <rule>: <reason, 10+ characters>
```

Rules: `migration`, `models`, `eligibility`, `scoring`, `ingestion`, `scheduling`, `hosting`, `milestone`. The guard catches a missing document edit, not a wrong one: review still owns correctness.
