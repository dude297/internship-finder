# Data Model

## Current Database State

Not configured yet. The database is selected (Neon PostgreSQL, [ADR-004](decisions/ADR-004-technology-stack.md)) but not provisioned. No schema or migrations exist.

## Planned Core Entities

**All entities below are planned.** They don't exist until an Alembic migration creates them. Fields are indicative, not final.

| Entity | Purpose | Indicative fields |
|---|---|---|
| `profile` | The user's canonical eligibility and fit inputs | id (UUID), **time-aware education status** (see below), date of birth (only if voluntarily stored), location, preferred locations, remote preference, availability windows, citizenship / work authorization, timestamps |
| `profile_sources` | Raw user-owned source material, kept unchanged | id (UUID), kind (resume / transcript / course list / GitHub / manual / …), original content or file reference, uploaded_at |
| `profile_facts` | Structured facts extracted from sources, with provenance | id (UUID), category (skill / course / project / award / …), value, source kind, profile_source_id (nullable), extraction method (manual / parser / AI model + version), confidence, verified_by_user, timestamps |
| `opportunities` | Normalized opportunity records | id (UUID), source, external_id, title, organization, url, location, **start date**, end date, deadline, requirements, raw payload, first_seen_at, last_seen_at, timestamps |
| `evaluations` | Eligibility + fit result for a profile/opportunity pair | id (UUID), opportunity_id, eligibility_status, eligibility_reasons, eligibility_rules_version, reference date(s) used, whether the result depends on projected status, fit_score, score_breakdown, scoring_version, evaluated_at |
| source metadata / ingestion runs | Per-source config and per-run summaries | source name, last run, counts (fetched/normalized/duplicates/invalid/errors), status, timestamps |
| application state | The user's application tracking | opportunity_id, status, submitted_at, notes, timestamps |

### Time-aware education status (planned)

Education status isn't a single static field. The profile stores dated status so eligibility can project the user's status at any date ([ADR-005](decisions/ADR-005-source-and-profile-ingestion-strategy.md)):

- current education level (e.g. high school)
- current grade/year (e.g. senior)
- expected graduation date
- expected college enrollment date
- expected future education level (e.g. undergraduate)

The current user is a high-school senior expected to become an undergraduate. Once actual graduation or enrollment happens, the profile is updated from expected to actual.

### Provenance rules (planned)

- `profile_sources` rows are never overwritten by parsing. Re-parsing creates new `profile_facts`.
- Every `profile_facts` row records its source and extraction method.
- AI-inferred facts are unverified until the user confirms them. Hard eligibility inputs come only from user-entered or user-verified data.

Where original uploaded files are stored is decided at implementation. No external object storage is used initially ([ADR-004](decisions/ADR-004-technology-stack.md)).

Design rules from [ENGINEERING_GUIDELINES.md §6](../ENGINEERING_GUIDELINES.md#6-database-standards) apply: UUID primary keys, external IDs stored separately, UTC timestamps, and constraints for real invariants. Authorization is enforced in the FastAPI backend.

## Keeping This File in Sync

- Every migration that changes the schema must update this file in the same change.
- When an entity moves from planned to real, replace its row with the actual columns, constraints, and the migration that created it.
- Migrations are the source of truth. If this file and the migrations disagree, the migrations win and this file is a bug.
