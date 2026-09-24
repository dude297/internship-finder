# Engineering Guidelines

This is the authoritative engineering standards document for the Personal Internship Finder. Where another document conflicts with this one, this one wins unless an accepted ADR in [`docs/decisions/`](docs/decisions/) says otherwise.

> **Stack note:** No application stack has been chosen or committed yet (see [`PROJECT_STATE.md`](PROJECT_STATE.md)). Language-specific guidance below (TypeScript, Zod, Supabase/RLS) applies **if and when** that stack is adopted. Update this file when the stack is decided.

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

Also validate migrations and RLS policies where applicable. The concrete commands are listed in [`docs/development.md`](docs/development.md) once they exist.

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

### TypeScript (if adopted)

- Use strong typing. Avoid `any` unless justified in a comment.
- Prefer domain-specific types:

```ts
type EligibilityStatus =
  | "eligible"
  | "ineligible"
  | "needs_verification";
```

- Use schema validation (e.g. Zod, if the stack includes it) at external boundaries: forms, API routes, source responses, imported JSON, AI output.

### Functions

Prefer clear, single-purpose functions:

```ts
evaluateEligibility(profile, opportunity)
```

Avoid catch-all functions:

```ts
processEverything(data)
```

### File Size

Treat very large files as a warning sign. General guidance (not hard limits):

- services/utilities: preferably under roughly 300–400 lines
- UI components: preferably under roughly 250–300 lines

### Comments

Comments explain **why**, assumptions, or non-obvious constraints. Do not comment obvious syntax.

---

## 6. Database Standards

- Use migrations for all schema changes.
- No undocumented manual production schema changes.
- Prefer UUIDs for application entities.
- Keep external source IDs in separate columns from internal IDs.
- Store timestamps consistently, preferably in UTC.
- Use database constraints for real invariants.
- Do not rely only on frontend validation.
- Use Row Level Security (RLS) if Supabase Auth / user-owned data is used.
- Never expose service-role credentials to the browser.
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

---

## 8. AI Usage Rules

AI is an **enrichment layer, not the source of truth**. See [ADR-003](docs/decisions/ADR-003-ai-as-enrichment.md).

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

```ts
interface OpportunitySource {
  sourceName: string;
  fetch(): Promise<RawOpportunity[]>;
  normalize(raw: RawOpportunity): NormalizedOpportunity;
}
```

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

### Integration Tests

For:

- database behavior
- ingestion
- API routes
- auth/RLS
- source adapters, where practical

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
