# Engineering Guidelines

This is the authoritative engineering standards document for the Personal Internship Finder. Where another document conflicts with this one, this one wins unless an accepted ADR in [`docs/decisions/`](docs/decisions/) says otherwise.

> **Stack note:** The stack is selected in [ADR-004](docs/decisions/ADR-004-technology-stack.md): a React/TypeScript/Vite/Tailwind frontend, a Python/FastAPI/Pydantic backend, and Neon PostgreSQL via SQLAlchemy/Alembic. Operating cost is **$0/month with no payment method required**. The frontend, backend, and database foundation are scaffolded locally (Milestone 0). No hosting or database is provisioned or deployed (see [`PROJECT_STATE.md`](PROJECT_STATE.md)).

---

## 1. Purpose

The project should remain:

- reliable
- secure
- maintainable
- testable
- easy to review
- suitable for AI-assisted development
- production-minded, even though it initially serves one user

### Roles

- **Claude** is the implementation engineer.
- **ChatGPT / human reviewer** acts as the architecture and review gate.
- Implementation is **not complete until reviewed**. Generated code is a proposal, not an accepted change.

---

## 2. Core Engineering Principles

### Production First

- No throwaway code merged into `main`.
- Validation, failure handling, tests, and documentation are part of feature completion, not follow-up work.

### Simple Before Clever

Prefer:

- clear code
- explicit control flow
- small modules
- understandable schemas

Avoid:

- premature abstraction
- unnecessary frameworks
- speculative architecture
- unnecessary dependencies

### Zero Cost

- Required services must work at **$0/month without a payment method**: no credit card, paid plan, usage-based billing, or paid overages.
- When a free-tier limit is hit, pause, throttle, fail visibly, or defer. Never escalate to paid usage.
- Any required dependency that needs payment information, can generate charges, or requires a paid plan needs a **new ADR before adoption** ([ADR-004](docs/decisions/ADR-004-technology-stack.md)).

### Separation of Concerns

Keep these areas logically separated:

| Area | Responsibility |
|---|---|
| Ingestion | Orchestrates fetching and processing runs |
| Source adapters | Fetch raw data from one source each |
| Normalization | Convert raw source records to a common shape |
| Deduplication | Detect the same opportunity across runs/sources |
| Persistence | The only layer that writes opportunity records |
| Eligibility | Deterministic qualification assessment |
| Scoring | Personalized fit score |
| Ranking | Ordering using eligibility + score |
| AI enrichment | Optional interpretation layered on source data |
| Application tracking | User's application state |
| Notifications | Alerts and digests |
| Profile ingestion | Raw profile sources → facts with provenance → user review |
| UI | Presentation only; no business rules |
| Observability | Logs, run summaries, metrics |

---

## 3. Repository Workflow Rules

### Main Branch

- `main` must remain usable at all times.
- Large feature work happens on feature branches.

Recommended branch names:

```text
feature/profile-schema
feature/manual-import
feature/eligibility-engine
feature/greenhouse-collector
fix/opportunity-dedupe
refactor/scoring-service
docs/architecture-update
```

### Scope

One branch represents one logical change. Do not mix unrelated:

- refactors
- dependency upgrades
- formatting
- features
- database work

unless it's actually required, and if it is, say why in the report.

### Commit Format

Use Conventional Commit-style messages:

```text
feat: add deterministic eligibility engine
fix: prevent duplicate source imports
test: cover ambiguous education requirements
docs: document opportunity ingestion pipeline
refactor: simplify scoring service
```

Avoid vague messages:

```text
update
changes
stuff
final
fixes
```

---

## 4. Implementation Workflow

Follow this for every feature task.

### Step 1 — Read Before Writing

Inspect:

- relevant files
- existing patterns
- utilities
- schema dependencies
- tests
- current behavior

Do not create duplicate architecture. Reuse what exists.

### Step 2 — Plan

Before major changes, briefly identify:

- files likely to change
- database/schema impact
- API impact
- assumptions
- risks
- testing plan

### Step 3 — Implement the Minimum Correct Change

Do not introduce unrelated changes.

### Step 4 — Validate

Run all applicable checks:

```text
lint
typecheck
unit tests
integration tests
build
```

Also validate migrations where applicable. The concrete commands are listed in [`docs/development.md`](docs/development.md) once they exist.

### Step 5 — Report

Every implementation task reports:

- summary
- files changed
- database changes
- tests/build results (only checks actually run)
- manual verification
- docs updated
- limitations
- risks
- recommended next task

---

## 5. Code Standards

### Python (backend)

- Modern type hints everywhere. Checked with Pyright (or equivalent) and linted/formatted with Ruff.
- Avoid `Any` unless justified in a comment.
- Prefer explicit domain types: Pydantic models, enums, dataclasses, `TypedDict`.

```python
class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    NEEDS_VERIFICATION = "needs_verification"
```

- Validate with Pydantic at every external boundary: API requests/responses, source adapter output, normalized opportunities, imported profile data, configuration, and AI output.
- SQLAlchemy 2.x for DB access. Avoid unnecessary ORM abstractions, and use raw SQL where it's clearer or more efficient. Schema changes go through Alembic.

### TypeScript (frontend)

- `strict` mode, ESLint, Prettier. Avoid `any` unless justified in a comment.
- Use Zod where runtime validation is useful (e.g. API responses, forms). Backend validation is authoritative. Don't duplicate complicated business rules in the frontend.
- Core business logic (eligibility, scoring, ranking, normalization, dedupe) lives in the backend, not in components.

### Functions

Prefer clear, single-purpose functions:

```python
evaluate_eligibility(profile, opportunity, reference_date)
```

Avoid catch-all functions:

```python
process_everything(data)
```

### File Size

Treat very large files as a warning sign. General guidance (not hard limits):

- services/utilities: preferably under roughly 300–400 lines
- UI components: preferably under roughly 250–300 lines

### Comments

Comments explain **why**, assumptions, or non-obvious constraints. Do not comment obvious syntax.

---

## 6. Database Standards

- Use migrations (Alembic) for all schema changes.
- No undocumented manual production schema changes.
- Prefer UUIDs for application entities.
- Keep external source IDs in separate columns from internal IDs.
- Store timestamps consistently, preferably in UTC.
- Use database constraints for real invariants.
- Do not rely only on frontend validation.
- Enforce authorization in the FastAPI backend. Postgres Row Level Security may be added if it's ever needed.
- Never expose database credentials or other secret keys to the browser. Anything in the Vite client bundle is public.
- Keep original source data (raw opportunity payloads, raw profile sources) alongside derived data. Never overwrite it.
- Do not trust client-provided ownership IDs; derive ownership server-side from the authenticated session.

Keep [`docs/data-model.md`](docs/data-model.md) in sync with migrations.

---

## 7. Security Standards

Never commit:

- API keys
- passwords
- service-role keys
- tokens
- credentials

Maintain [`.env.example`](.env.example) with placeholders only.

Validate all untrusted input, including:

- forms
- crawler/scraped data
- API responses
- imported JSON
- AI-generated structured output

Additional rules:

- Treat external opportunity descriptions as untrusted content.
- Do not render raw HTML unless it has been safely sanitized.
- Authorization checks happen server-side.

The repository is public. Privacy, secrets, CI, and dependency rules for public code are in [§16](#16-public-repository-security-and-privacy).

---

## 8. AI Usage Rules

AI is an **enrichment layer, not the source of truth**. See [ADR-003](docs/decisions/ADR-003-ai-as-enrichment.md).

AI is **optional**. The core application must work without any paid AI API, paid embedding API, or paid vector database ([ADR-004](docs/decisions/ADR-004-technology-stack.md)). Future AI may use local models (e.g. Ollama), manually triggered inference, free allocations, or pluggable provider adapters.

AI-inferred **profile facts** are stored with provenance (source, model/version, confidence) and are unverified until the user confirms them. Hard eligibility never uses unverified inferred facts ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)).

AI may assist with:

- requirement extraction
- classification
- summarization
- semantic matching
- explanation generation
- identifying uncertainty

AI must **not** be the sole authority for:

- age eligibility
- legal work authorization
- deadlines
- citizenship requirements
- education requirements
- whether a posting exists
- whether an application was submitted

Hard eligibility rules should be deterministic wherever possible.

Structured AI output must:

- follow a schema
- be validated before use
- preserve the raw source data alongside it
- handle failures without breaking the pipeline
- record model/version where appropriate
- surface uncertainty rather than hide it

---

## 9. Opportunity Source Standards

All collectors share a common concept (illustrative; the final shape is decided at implementation):

```python
class OpportunitySource:
    async def fetch(self) -> list[RawOpportunity]: ...
    def normalize(self, raw: RawOpportunity) -> NormalizedOpportunity: ...
```

Transport may differ per source. The common boundary starts after fetch. Prefer structured sources (public feeds, ATS APIs) over HTML parsing, and HTML parsing over browser automation ([ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md)).

External open-source projects are references or optional sources, never foundations, unless explicitly approved. Before copying any code, check the license, compatibility, attribution, and copyleft obligations, and document the reuse. Don't copy AGPL code (e.g. Kestrel) without separate licensing review and approval.

Source connectors should support:

- source attribution
- stable external IDs when available
- last-seen tracking
- deduplication
- error reporting

Connectors feed the **shared ingestion pipeline** and do not write arbitrary records to the database themselves. See [ADR-002](docs/decisions/ADR-002-shared-ingestion-pipeline.md) and [`docs/sources.md`](docs/sources.md).

---

## 10. Failure Handling

Expected failures must not crash the entire ingestion process. Examples:

- one source unavailable
- malformed record
- timeout
- duplicate
- missing optional fields
- AI parsing failure

Prefer partial success with measurable output:

```text
150 fetched
143 normalized
4 duplicates
2 invalid
1 source error
```

Errors must be observable and diagnosable. Never silently swallow them.

---

## 11. Logging and Observability

Use structured logging that includes, where relevant:

- source
- operation
- record counts
- status
- timing (where helpful)
- error category

Do not log secrets or unnecessary sensitive profile data.

Future scheduled jobs must produce run summaries. See [`docs/operations.md`](docs/operations.md).

---

## 12. Testing Standards

### Unit Tests

For:

- eligibility
- scoring
- normalization
- deduplication
- ranking
- parsing

Backend tests use Pytest. Frontend tests use Vitest (plus React Testing Library where useful). Time-aware eligibility rules are tested on both sides of graduation and enrollment dates.

### Integration Tests

For:

- database behavior
- ingestion
- API routes
- authorization
- source adapters, where practical

### End-to-End Tests

Playwright, for critical user flows once they exist.

### Regression Tests

Bug fixes add a regression test when reasonably possible.

Core business logic must be testable independently of the UI.

---

## 13. Production Gate

Before merging to `main`:

```text
[ ] lint passes
[ ] typecheck passes
[ ] tests pass
[ ] build passes
[ ] migrations reviewed
[ ] environment variables documented
[ ] security impact reviewed
[ ] errors handled
[ ] docs updated
[ ] no unrelated changes
```

Any exception must be documented explicitly in the PR/report, with a reason.

---

## 14. Definition of Done

A task is complete only when:

1. requested behavior works
2. code follows project conventions
3. tests pass
4. errors are handled
5. security implications are addressed
6. documentation is updated
7. unrelated regressions are not introduced
8. an implementation summary is provided
9. review is complete

**"Code written" does not equal "done."**

---

## 15. Documentation Maintenance Rules

Documentation changes are part of the Definition of Done.

Update [`PROJECT_STATE.md`](PROJECT_STATE.md) after:

- completing a milestone
- architecture changes
- database changes
- adding/removing sources
- introducing known issues
- changing next planned work

Update ADRs when an architectural decision changes. **Do not silently rewrite accepted ADR history.** Instead:

1. mark the old ADR as `Superseded by ADR-XXX`
2. create a new ADR

Keep topic docs in sync:

| Change | Update |
|---|---|
| Schema / migrations | [`docs/data-model.md`](docs/data-model.md) |
| Eligibility rules | [`docs/eligibility.md`](docs/eligibility.md) |
| Scoring model | [`docs/scoring.md`](docs/scoring.md) |
| Ingestion sources | [`docs/sources.md`](docs/sources.md) |
| Production process | [`docs/deployment.md`](docs/deployment.md) |
| Runtime / monitoring | [`docs/operations.md`](docs/operations.md) |
| Setup / scripts | [`docs/development.md`](docs/development.md), [`README.md`](README.md) |
| Notable changes | [`CHANGELOG.md`](CHANGELOG.md) |

---

## 16. Public Repository Security and Privacy

The repository (`dude297/internship-finder`) is public. This is a permanent constraint unless a future governance decision changes it. The short rules are in [`CLAUDE.md`](CLAUDE.md#public-repository-safety).

### Public by Default

Anything committed to Git should be assumed permanently public. That includes commit messages and author metadata.

Deleting a file in a later commit does not remove it from Git history. A committed secret must be rotated, and the history must be rewritten. Forks, clones, and GitHub pull request refs may keep copies anyway.

### No Personal Source Documents

User-owned private source documents must not be committed. Examples:

- résumé
- transcript
- application essays
- recommendation letters
- school records
- personal profile exports

These belong in local ignored storage, protected application storage, or the database where appropriate. They never belong in Git.

### Public Code / Private Data Boundary

The repository holds code and generic material only. Personal data exists only at runtime, outside Git:

```text
PUBLIC REPOSITORY

application code
schemas
migrations
synthetic fixtures
documentation
generic examples

            │
            │ runtime boundary
            ▼

PRIVATE USER DATA

résumé
profile sources
transcripts
application history
personal facts
credentials
private files
```

This boundary is mandatory. Future personal data includes the résumé, coursework, projects, awards, application history, preferences, and personal profile facts. None of it is stored in the repository ([ADR-005 clarification](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md#clarification-2026-09-25-public-repository-boundary)).

### Synthetic Test Data

Tests use synthetic or deliberately anonymized fixtures.

Do not copy real résumé text, school records, application responses, addresses, phone numbers, or other private material into test fixtures or documentation examples.

### Logs

Do not commit runtime logs containing:

- credentials
- authorization headers
- personal profile data
- résumé contents
- database URLs
- tokens

### Screenshots

Before committing screenshots, inspect them for:

- account names
- email addresses
- browser tabs
- URLs with tokens
- local filesystem paths
- personal profile information

### GitHub Issues and Pull Requests

Do not paste secrets or private profile content into issues, PR descriptions, review comments, or Actions logs.

GitHub discussions around this repository should also be treated as public.

### Environment Files

- Only `.env.example` files with placeholders are tracked. `.gitignore` ignores `.env` and `.env.*` in every directory, except `.env.example`.
- Local storage for private user files (uploads, exports, dumps) must be gitignored before any code writes to it.

### GitHub Actions

Forks and external pull requests may exist. Treat contributions as untrusted input.

- Workflows use minimum permissions. Prefer a top-level `permissions: contents: read`, and grant more only per job, with a documented reason.
- Do not expose secrets to forked PRs. Do not run untrusted PR code with privileged secrets.
- Avoid `pull_request_target` unless the workflow is specifically security-reviewed.
- Pin or deliberately review third-party actions before use.
- Never put secrets in workflow YAML. Use repository or environment secrets when they eventually become necessary.
- No production secrets are currently required.

### Dependency Security

Supply-chain configuration is also public.

- Avoid unnecessary dependencies.
- Review third-party packages and actions before adoption.
- Keep lockfiles where appropriate (`frontend/package-lock.json`).
- Use Dependabot or an equivalent only if explicitly approved later.
- Don't copy arbitrary code from GitHub. The license-review rules in [ADR-005](docs/decisions/ADR-005-source-and-profile-ingestion-strategy.md) remain in force.
