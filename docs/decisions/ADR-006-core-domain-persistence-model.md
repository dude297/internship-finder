# ADR-006: Core Domain Persistence Model

Status: Accepted (pending review of the Milestone 1 PR)

Date: 2026-09-25

## Context

[ADR-005](ADR-005-source-and-profile-ingestion-strategy.md) set conceptual shapes for a time-aware profile, provenance-aware profile facts, and layered opportunity sources. [ADR-001](ADR-001-separate-eligibility-and-fit.md) requires evaluations to record eligibility status, reasons, and the rules version. Milestone 1 turns these into real tables, a first Alembic migration, and eligibility rules v1. Several choices here are hard to change once data exists, so they're recorded here.

## Decision

### 1. Canonical profile fields vs profile facts

- `profiles` holds the **canonical** values: user-entered or user-confirmed. Hard eligibility reads **only** these columns (education timeline, date of birth, citizenships).
- `profile_facts` holds structured facts extracted or entered from sources, with provenance (source kind, extraction method, extractor name/version, confidence, `verified_by_user`). Facts are inputs to future fit scoring and to user review. They are **never** read by the eligibility engine, verified or not. Promoting a fact to a canonical field is an explicit user action (a later milestone).
- This makes "hard eligibility never uses an unverified AI inference" structural, not a runtime check.

### 2. Temporal education is a timeline, not a level

The profile stores `current_education_level` plus the date it was true (`education_status_as_of`), `expected_graduation_date`, `expected_enrollment_date`, and `expected_future_education_level`. A pure resolver (`app.profile.education.resolve_education_status`) projects it to any reference date as `(phase, level, projected)`, where phase is `enrolled`, `incoming`, or `unknown`. `unknown` means insufficient information. The resolver never guesses. The semantics are in [docs/eligibility.md](../eligibility.md#temporal-education-resolver).

### 3. Requirements are structured records

`opportunity_requirements` holds one row per hard requirement: `requirement_type`, a JSON `value` validated by a per-type Pydantic schema, `applies_at` (`application` / `program_start` / `explicit_date`), an optional explicit `reference_date`, the evidence text, and extraction provenance. Manual entry, future deterministic parsers, and future AI extraction all produce this same shape. Requirement types without a v1 rule (`work_authorization`, `other`) produce `needs_verification`. They are never silently ignored.

Whether the requirement rows are the **full** set is stored separately on the opportunity as `requirements_assessment_status` (`unassessed` default / `partial` / `complete`). It's an enum rather than a boolean because never-assessed and partly-assessed need to stay distinct. It's never inferred from the row count, because zero requirements can be legitimate. Eligibility records it as rule ELIG-REQ-000: anything short of `complete` is at least `needs_verification` ([eligibility.md](../eligibility.md#requirement-assessment)). Added in PR review, before Milestone 1 was merged, by editing the initial migration.

### 4. Opportunity source provenance is separate from the canonical record

`opportunities` is the source-independent record. `opportunity_source_records` stores each sighting (source name/type, external ID, URL, raw payload, fetched/first/last seen). `(source_name, external_id)` is unique; rows without an external ID don't collide. A future deduplicator can attach several source records to one opportunity without schema changes.

### 5. Evaluations are history

`opportunity_evaluations` gets a new row each time eligibility is evaluated. Rows are never overwritten. "Current" means the latest `evaluated_at` per (profile, opportunity). Each rule's outcome is a row in `eligibility_rule_results` (rule ID, status, reason, reference date, projected flag, structured details, and the requirement it evaluated). This keeps explanations queryable instead of storing a single opaque reasons string. Fit-scoring columns (`fit_score`, `score_breakdown`, `scoring_version`) are **not** added until scoring v1 exists. That migration adds them as nullable columns.

### 6. Portable column types

- UUID primary keys (`sa.Uuid`), `timestamptz` timestamps (`DateTime(timezone=True)`), plain `Date` for calendar dates.
- Enums are `VARCHAR(32)` + a named CHECK constraint (SQLAlchemy `Enum(native_enum=False)`). There are no Postgres enum types, so downgrade is a plain table drop, and adding a value is a CHECK change.
- Heterogeneous values (`profile_facts.value`, `opportunity_requirements.value`, raw payloads, rule details, citizenship lists) use portable `sa.JSON`. JSONB isn't needed until we query inside these values.
- Real invariants are CHECK constraints: confidence in [0, 1]; AI-inferred rows name their extractor; education level ⇔ as-of date; enrollment not before graduation; end not before start; last seen not before first seen; `reference_date` present iff `applies_at = explicit_date`.

### 7. Deletion

Profile rows cascade to their sources, facts, and evaluations. Deleting private data removes all of it. Rule results keep their text if the requirement they evaluated is deleted (`requirement_id` set to NULL).

## Consequences

- The eligibility engine takes Pydantic inputs built from ORM rows (`model_validate`), so it's testable without a database.
- Preferences, remote preference, and availability are not canonical columns yet. They're fit inputs and arrive with scoring (as facts or a migration).
- Schema and migration correctness are tested only against real PostgreSQL (CI service container), not SQLite.
- Re-evaluation is explicit: nothing recomputes evaluations automatically yet.

## Alternatives Considered

- **One JSON document for the whole profile.** Flexible, but no constraints and no provenance per value. Rejected.
- **Requirements only as description text.** Rules would need to parse prose on every evaluation, and nothing would be auditable. Rejected.
- **Source fields (`source`, `external_id`, raw payload) on `opportunities`.** Simple, but one opportunity seen by two sources would need a redesign. Rejected.
- **Overwrite a single evaluation row per pair.** Smaller, but it loses the history of why a status changed (for example, after a profile update). Rejected.
- **Native Postgres enums / JSONB.** Faster queries later, but they complicate downgrades and aren't needed yet. Can be revisited with a migration.
