# Data Model

## Current Database State

Not configured yet. No database, schema, or migrations exist.

## Planned Core Entities

**All entities below are planned.** They don't exist until a migration creates them. Fields are indicative, not final.

| Entity | Purpose | Indicative fields |
|---|---|---|
| `profile` | The user's eligibility and fit inputs | id (UUID), date of birth / age, education level & enrollment, citizenship / work authorization, skills, interests, location preferences, timestamps |
| `opportunities` | Normalized opportunity records | id (UUID), source, external_id, title, organization, url, location, deadline, requirements, raw payload, first_seen_at, last_seen_at, timestamps |
| `evaluations` | Eligibility + fit result for a profile/opportunity pair | id (UUID), opportunity_id, eligibility_status, eligibility_reasons, eligibility_rules_version, fit_score, score_breakdown, scoring_version, evaluated_at |
| source metadata / ingestion runs | Per-source config and per-run summaries | source name, last run, counts (fetched/normalized/duplicates/invalid/errors), status, timestamps |
| application state | The user's application tracking | opportunity_id, status, submitted_at, notes, timestamps |

Design rules from [ENGINEERING_GUIDELINES.md §6](../ENGINEERING_GUIDELINES.md#6-database-standards) apply: UUID primary keys, external IDs stored separately, UTC timestamps, constraints for real invariants, and RLS if user-owned data uses Supabase Auth.

## Keeping This File in Sync

- Every migration that changes the schema must update this file in the same change.
- When an entity moves from planned to real, replace its row with the actual columns, constraints, and the migration that created it.
- Migrations are the source of truth. If this file and the migrations disagree, the migrations win and this file is a bug.
