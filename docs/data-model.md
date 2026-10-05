# Data Model

## Current Database State

The schema is created by six Alembic migrations in `backend/alembic/versions/`:

| Revision | Milestone | Tables |
|---|---|---|
| `3b9c6b57bb60` (initial core domain schema) | 1 (merged, **immutable**) | `profiles`, `profile_sources`, `profile_facts`, `opportunities`, `opportunity_source_records`, `opportunity_requirements`, `opportunity_evaluations`, `eligibility_rule_results` |
| `7d7f4f8b9a3c` (auth sessions and application tracking) | 2 (merged) | `auth_users`, `auth_sessions`, `applications`; adds `ck_profiles_graduation_after_status_as_of` to `profiles` |
| `726372d627b8` (opportunity ingestion and deduplication) | 3 | `ingestion_sources` (seeds the built-in discovery feed), `ingestion_runs`, `ingestion_run_errors`, `opportunity_identifiers`; new columns on `opportunities`, `opportunity_source_records`, `opportunity_evaluations`; reconciles `ck_profiles_graduation_after_status_as_of` (below) |
| `92a17353e5a8` (reconcile the one-running-ingestion-run index) | 3.5 | No new tables or columns; ensures `uq_ingestion_runs_one_running_per_source` exists (below) |
| `b41e7c9d2f60` (fit scoring v1, Match Profile preferences, and ATS source scope) | 4 | No new tables. `profiles`: fit preferences; `opportunity_evaluations`: fit columns; `ingestion_sources.scope`; `ingestion_runs.filtered_count` (below) |
| `c5a1e0f3d7b2` (profile source ingestion and fact review state) | 5 | `profile_source_artifacts`; upload metadata on `profile_sources`; `profile_facts.review_state` (below) |

The design rationale is in [ADR-006](decisions/ADR-006-core-domain-persistence-model.md) (core domain), [ADR-007](decisions/ADR-007-single-user-auth-and-private-api.md) (authentication), [ADR-008](decisions/ADR-008-opportunity-ingestion-and-deduplication.md) (ingestion), [ADR-010](decisions/ADR-010-fit-scoring-v1.md) (fit scoring, Match Profile, source scope), and [ADR-011](decisions/ADR-011-profile-source-ingestion-and-review.md) (profile source uploads and review). The migrations are verified in CI against a disposable PostgreSQL 18 container (upgrade → `alembic check` → downgrade → upgrade, plus integration tests that step through every revision). The hosted Neon database is at `c5a1e0f3d7b2` (Milestone 5, applied 2026-10-01, [deployment.md](deployment.md#milestone-5-release-2026-10-01)). Locally, `compose.yaml` runs a development PostgreSQL 18.

ORM models are in `backend/app/models/`. Shared enums are in `backend/app/enums.py`.

### Graduation-constraint reconciliation (`726372d627b8`)

`ck_profiles_graduation_after_status_as_of` was added to `7d7f4f8b9a3c` during PR #5 review, before it merged. A development database upgraded with the earlier local version of `7d7f4f8b9a3c` reports that revision but lacks the constraint (`alembic check` doesn't compare CHECK constraints). `726372d627b8` repairs this automatically: on upgrade it looks the constraint up in `pg_constraint` and creates it only if it's missing (fresh databases already have it from `7d7f4f8b9a3c`). No manual SQL is needed.

The reconciliation is intentionally **asymmetric**: downgrading `726372d627b8` leaves the constraint in place, because it's part of `7d7f4f8b9a3c`'s intended final schema; downgrading further to `3b9c6b57bb60` removes it (that's `7d7f4f8b9a3c`'s own downgrade). As with `7d7f4f8b9a3c`, a stored profile that violates the rule makes the upgrade fail; fix the dates and upgrade again. `tests/test_migrations.py` simulates the stale database (upgrade to `7d7f4f8b9a3c`, drop the constraint, upgrade to head) and checks the constraint comes back.

### Running-run index reconciliation (`92a17353e5a8`)

`uq_ingestion_runs_one_running_per_source` (partial UNIQUE on `ingestion_runs(source_id)` WHERE `status = 'running'`) was added to `726372d627b8` during PR #6 review, before it merged. A development database upgraded with the earlier local version of `726372d627b8` reports that revision but lacks the index. `92a17353e5a8` looks the index up in the PostgreSQL catalog on upgrade and creates it only if it's missing; on a fresh database it's a no-op. Before creating it, the upgrade checks for sources with more than one `running` run and, if any exist, fails with a message naming them rather than choosing one or deleting history: mark the stale runs `failed` (with `finished_at`), then upgrade again. One running run per source is fine.

Like the graduation-constraint repair, it's **asymmetric**: downgrading `92a17353e5a8` leaves the index in place, because it belongs to `726372d627b8`'s intended final schema; downgrading `726372d627b8` itself drops it. `tests/test_migrations.py` covers the stale path (upgrade to `726372d627b8`, drop the index, upgrade to head), the duplicate-running refusal, and the fresh path.

### Milestone 4 migration (`b41e7c9d2f60`)

Adds nullable columns only (plus `ingestion_sources.scope`, backfilled with `all` for every existing source so an upgrade never starts filtering, then made NOT NULL, and `ingestion_runs.filtered_count` with default 0). Existing evaluations keep NULL fit fields and stay valid. Downgrading to `92a17353e5a8` drops the new columns and constraints (fit results, fit preferences, and scopes are lost; eligibility history is kept). `tests/test_migrations.py` covers the round trip, the `all` backfill for a pre-existing board, and each new constraint.

### Milestone 5 migration (`c5a1e0f3d7b2`)

Creates `profile_source_artifacts`, adds nullable upload metadata to `profile_sources` plus `UNIQUE (profile_id, content_sha256)`, and adds `profile_facts.review_state` with a server default of `accepted`. The column is added with that default (PostgreSQL fills every existing row with it), then non-manual unverified rows are updated to `pending` — the same backfill as before, just reached in the opposite direction — so the upgrade still changes no fit input; then the column becomes NOT NULL. The default stays on the column after the migration (it is not dropped): it exists so the immediately previous (Milestone 4) application, whose manual Match Profile inserts don't name `review_state`, can still save after this migration is applied and before Milestone 5 is deployed, and so a Render rollback to Milestone 4 doesn't break. It is not an invitation for Milestone 5 code to omit `review_state` — every Milestone 5 write still states it explicitly — and the `review_state_matches_verified` CHECK rejects an unverified non-manual insert that omits it, since the default only produces `accepted`. Downgrading to `b41e7c9d2f60` drops the table, columns, and constraints (uploaded files and review states are lost; imported pending/rejected facts are unverified, so the Milestone 4 filter still ignores them). `tests/test_migrations.py` covers the backfill for every provenance combination, the round trip, each new constraint, the source cascade, the default's deployment-compatibility behavior at head, and that `fit_profile_input` selects the same facts the Milestone 4 filter did.

All tables contain **private runtime data**. Nothing from them is ever committed ([ENGINEERING_GUIDELINES.md §16](../ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy)).

### Milestone 6 migration (`e6d1a4b8c2f9`)

Additive ([ADR-012](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)): the `opportunity_requirement_candidates` table, `opportunities.requirements_stale_since` and `opportunities.requirement_extraction_fingerprint` (both nullable, no backfill), and `'ashby'` in the `ingestion_sources.kind` CHECK. No data is rewritten, nothing is evaluated, and no network is used, so the Milestone 5 application keeps working on the upgraded schema. Downgrade drops the table and columns (review decisions on suggestions are lost; canonical requirements created by accepting them stay) and refuses while an Ashby source exists. **Code rollback without a schema downgrade:** the Milestone 5 code can't read an `ashby` row (its enum has no such value), so `GET /api/sources` and sync would fail. Before rolling the code back to Milestone 5 while keeping this schema, disable and remove any Ashby source (or downgrade properly). Verified locally on PostgreSQL 18: base → head, `alembic check`, head → `c5a1e0f3d7b2` → head, base → head; `tests/test_migrations.py` also checks row preservation and the Ashby guard.

### Milestone 7.1 migration (`f2a7c9d4e1b3`)

Additive: `'volunteer'` in the `opportunities.opportunity_type` CHECK. No row changes and no backfill (existing `other` rows stay `other`; nothing classifies postings as volunteer). Downgrade refuses while a volunteer opportunity exists. Eligibility and fit never read the type, so no evaluation changes. Compatibility: the Milestone 7 backend runs unchanged on the migrated schema (it just can't create a volunteer row); the Milestone 7.1 backend on the old schema works except creating/editing a volunteer opportunity (the CHECK rejects it), so migrate before deploying Render. **Release rule:** create no volunteer opportunity until the Milestone 7.1 frontend is live on Vercel (an older bundle's response schema has no `volunteer` value and would reject a whole list containing one); hard-reload open tabs after the deploy. **Rollback:** older backend code can't load a `volunteer` row (its enum lookup fails, so list and detail return `500`) and the downgrade refuses while one exists, so delete (or retype) volunteer opportunities before rolling Render or Vercel back to Milestone 7. Verified locally on PostgreSQL 18: base → head, head → `e6d1a4b8c2f9` → head, `alembic check`; `tests/test_migrations.py` covers the CHECK before/after, no backfill, and the downgrade guard.

### Milestone 8 migration (`a8c3e5f7b9d1`)

Additive ([ADR-014](decisions/ADR-014-structured-source-expansion-and-program-registry.md)): `'smartrecruiters'` and `'curated_registry'` in the `ingestion_sources.kind` CHECK; `'curated_registry'` in `opportunity_source_records.source_type`; the built-in scope rule (`builtin_scope_all`) covers the registry; nullable `opportunities.program_cycle` (≤ 20), `typical_open_window` (≤ 100), `typical_close_window` (≤ 100), and `verify_by` (date), no backfill; and one seeded row, the built-in **Curated Program Registry** source (`curated_registry` / `program-registry`, enabled, scope `all`). Only registry records write the new columns or the deadline/start/end dates; a typical window is text and never a date.

**Compatibility.** The Milestone 7.1 backend can't load the seeded `curated_registry` source (its enum has no such value), so `GET /api/sources` and any sync would fail between migrating and deploying: disable the scheduled workflow, migrate, and deploy Render immediately (runbook in [operations.md](operations.md#milestone-8-release-and-activation-notes-prepared-not-executed)). The Milestone 8 backend can't run on the old schema (new columns). The 7.1 frontend rejects the sources list once the registry exists, so deploy Vercel right after Render. **Downgrade** refuses while a SmartRecruiters source or any registry record exists (rather than deleting them), otherwise deletes the seeded registry source (and its run history) and drops the columns. Verified locally on PostgreSQL 18: base → head, head → `f2a7c9d4e1b3` → head, `alembic check`; `tests/test_migrations.py` covers the seeded row and the round trip.

### Conventions

- Primary key `id` is a UUID (generated by the application).
- Timestamps are `timestamptz`. `created_at`/`updated_at` default to `now()`. Calendar dates (birth, deadlines, graduation) are `date`.
- Enums are `varchar(32)` with a CHECK constraint listing the allowed values (no native Postgres enum types).
- Flexible values use `json`.
- Constraint names follow `app/db/base.py`: `pk_<table>`, `fk_<table>_<column>`, `uq_<table>_<columns>`, `ix_<table>_<columns>`, `ck_<table>_<name>`.
- Foreign keys are indexed.

## Tables

### `profiles`

The canonical profile: user-entered or user-confirmed values. It's the only input to hard eligibility.

| Column | Type | Notes |
|---|---|---|
| `current_education_level` | enum `high_school` / `undergraduate` / `graduate`, null | |
| `current_grade` | varchar(32), null | Display only (e.g. `"12"`) |
| `education_status_as_of` | date, null | The date `current_education_level` was true |
| `expected_graduation_date` | date, null | Leaves the current level on this date |
| `expected_enrollment_date` | date, null | Enters the future level on this date |
| `expected_future_education_level` | enum, null | |
| `date_of_birth` | date, null | |
| `citizenships` | json list of ISO 3166-1 alpha-2 codes, null | NULL = not provided. The API accepts only the 249 officially assigned codes (e.g. `GB`, not `UK`) |
| `work_authorizations` | json list of country codes, null | Stored; no v1 rule uses it |
| `location` | varchar(200), null | |
| `interests` | json list of strings, null | Fit input only (Milestone 4). NULL or empty = none |
| `preferred_locations` | json list of strings, null | Fit input only |
| `remote_preference` | enum `no_preference` / `remote_preferred` / `hybrid_preferred` / `onsite_preferred` / `remote_only`, null | Fit input only |
| `availability_start`, `availability_end` | date, null | Fit input only. CHECK `ck_profiles_availability_end_not_before_start` |
| `created_at`, `updated_at` | timestamptz | |

The Milestone 4 columns are Match Profile preferences ([ADR-010 §5](decisions/ADR-010-fit-scoring-v1.md#5-profile-inputs-match-profile)): eligibility never reads them, and `PUT /api/profile` doesn't change them.

Constraints: `ck_profiles_education_level_has_as_of` (level and as-of date are both set or both NULL), `ck_profiles_enrollment_not_before_graduation`, and `ck_profiles_graduation_after_status_as_of` (Milestone 2, migration `7d7f4f8b9a3c`).

**Education timeline invariant.** When both are set, `expected_graduation_date > education_status_as_of` (strict). The resolver applies the graduation transition **on** the graduation date, so a current level recorded on or after that date would claim both the pre- and post-graduation state at once (e.g. "high school as of 2041-09-01" with graduation on 2041-06-10 would let the resolver project undergraduate status over the authoritative current level). Missing dates are still allowed; a graduation date is never required. `PUT /api/profile` rejects a violation with `422` (`expected_graduation_date must be after education_status_as_of`), and the database constraint stops any code path that bypasses the API. This is input integrity, not an eligibility-rule change: the rules version stays `v1`.

### `profile_sources`

Metadata about a private source artifact (résumé, transcript, course list, GitHub, manual entry). Uploaded bytes live in `profile_source_artifacts`, never in Git or on disk ([ADR-011](decisions/ADR-011-profile-source-ingestion-and-review.md)). Milestone 5 uploads create `kind = resume` rows.

| Column | Type | Notes |
|---|---|---|
| `profile_id` | FK → `profiles`, cascade | |
| `kind` | enum `manual` / `resume` / `transcript` / `course_list` / `project` / `github` / `user_preference` / `other` | |
| `original_filename` | varchar(255), null | |
| `storage_ref` | varchar(1024), null | Opaque pointer into private storage |
| `content_sha256` | varchar(64), null | CHECK: 64 characters when present. UNIQUE with `profile_id`: the same file can't be uploaded twice |
| `details` | json, null | |
| `content_type` | varchar(100), null | Sniffed allowlisted type: `text/plain` or `application/pdf` |
| `byte_size` | integer, null | CHECK: > 0 when present |
| `parser_name`, `parser_version` | varchar, null | The parser that produced the current candidates (`resume-sections`, `1`) |
| `ingested_at` | timestamptz | |

`storage_ref` is unused: the artifact is found by the source's ID.

### `profile_source_artifacts`

The original uploaded bytes, written once, never updated, 1:1 with a source. Kept out of `profile_sources` so listing sources never reads file content. Only `GET /api/profile/sources/{id}/file` and re-parsing read it.

| Column | Type | Notes |
|---|---|---|
| `profile_source_id` | PK, FK → `profile_sources`, cascade | |
| `content` | bytea | At most 2 MB (enforced by the API) |

### `profile_facts`

Structured facts with provenance. Never read by hard eligibility (ADR-006 §1).

| Column | Type | Notes |
|---|---|---|
| `profile_id` | FK → `profiles`, cascade | |
| `profile_source_id` | FK → `profile_sources`, cascade, null | NULL for facts without a source document |
| `category` | enum `education` / `course` / `skill` / `project` / `award` / `activity` / `experience` / `research` / `preference` / `other` | |
| `fact_key` | varchar(100) | e.g. `python` |
| `value` | json | |
| `source_kind` | enum (same values as `profile_sources.kind`) | |
| `extraction_method` | enum `manual` / `deterministic_parser` / `ai_inference` | |
| `extractor_name`, `extractor_version` | varchar, null | CHECK: required when `ai_inference` |
| `confidence` | float, null | CHECK: 0–1 |
| `verified_by_user` | boolean, default false | |
| `review_state` | enum `pending` / `accepted` / `rejected`, server default `accepted` (deployment compatibility only, see below) | CHECK: a non-manual fact is `accepted` exactly when `verified_by_user` |
| `created_at`, `updated_at` | timestamptz | |

**Match Profile facts** (Milestone 4) are rows with `source_kind = manual`, `extraction_method = manual`, `verified_by_user = true`, `review_state = accepted`, no `profile_source_id`, `fact_key = match_profile.NNN` (position), and category `skill` or `course` (`value` = `{"name": str}`) or `project`, `research`, `activity`, `experience` (`value` = `{"name": str, "description": str | null}`). `PUT /api/profile/match` replaces only these rows; any other fact is left alone.

**Imported facts** (Milestone 5) come from `app.profile.resume_parser`: `source_kind = resume`, `extraction_method = deterministic_parser`, `extractor_name`/`extractor_version` = the parser, `profile_source_id` set, `review_state = pending`, `verified_by_user = false`, category `skill`, `course`, `project`, `research`, `experience`, `activity`, `award`, or `education` with the Match Profile value shapes. Accepting sets `accepted` and `verified_by_user = true` (value possibly edited); rejecting sets `rejected` and `false`. Fit v1 reads `skill`, `course`, `project`, and `research` facts with `review_state = accepted` (ADR-011 §5); a fact whose value doesn't have that shape is skipped (and logged), never coerced. `fact_key` is `resume.` + a hash of the original parsed (category, name) — a stable identity for the parsed candidate, not its position (M5.1; see ADR-011 §7 for why and for the pre-M5.1 `resume.NNN` legacy format).

### `opportunities`

Canonical, source-independent opportunity.

| Column | Type | Notes |
|---|---|---|
| `title`, `organization` | varchar | Required |
| `description` | text, null | |
| `opportunity_type` | enum `internship` / `research` / `fellowship` / `summer_program` / `scholarship` / `competition` / `volunteer` / `other` | `volunteer` since Milestone 7.1 (manual selection only; ingestion never emits it) |
| `application_url` | varchar(2048), null | |
| `location` | varchar(200), null | |
| `remote_mode` | enum `onsite` / `remote` / `hybrid`, null | |
| `application_deadline`, `start_date`, `end_date` | date, null | CHECK: end ≥ start |
| `requirements_assessment_status` | enum `unassessed` / `partial` / `complete`, default `unassessed` | Whether `opportunity_requirements` holds every hard requirement. Set explicitly, never inferred from the row count. Only `complete` lets zero requirements mean `eligible` ([ELIG-REQ-000](eligibility.md#elig-req-000)). Imported opportunities start `unassessed` |
| `first_seen_at`, `last_seen_at` | timestamptz | When any source first/last saw it (not a posting date). CHECK: last ≥ first |
| `posted_at` | timestamptz, null, indexed | When the source says it was published (feed `posted_at`, Greenhouse `first_published`, Lever `createdAt`). Never an ATS "updated" time. Discovery sorting only; eligibility doesn't read it (Milestone 3) |
| `manually_curated_at` | timestamptz, null | Set when the owner creates or edits the opportunity through the API. Sync never overwrites the canonical fields, requirements, or assessment of a curated opportunity. NULL for imported opportunities the owner hasn't edited. Backfilled from `updated_at` for opportunities that existed before Milestone 3 (Milestone 3) |
| `requirements_stale_since` | timestamptz, null | Set when a sync materially changed the posting text (title, description, deadline, start date) after the owner had reviewed its requirements; the owner's next review batch clears it. A `complete` assessment is downgraded at the same time ([ADR-012 §6](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md#6-lifecycle-and-staleness)) (Milestone 6) |
| `requirement_extraction_fingerprint` | varchar(64), null | SHA-256 of the extractor name, version, and extraction inputs at the last extraction. NULL = never extracted. CHECK: 64 characters (Milestone 6) |
| `created_at`, `updated_at` | timestamptz | |

### `opportunity_requirement_candidates`

Deterministic requirement suggestions and their owner review (Milestone 6, [ADR-012](decisions/ADR-012-opportunity-requirement-intelligence-and-automation.md)). **Never read by eligibility.**

| Column | Type | Notes |
|---|---|---|
| `opportunity_id` | uuid FK → opportunities, cascade | |
| `semantic_key` | varchar(64) | SHA-256 of type, normalized value, applies_at, and reference date. UNIQUE (`opportunity_id`, `semantic_key`). Never position, source text, IDs, or time |
| `requirement_type`, `value`, `applies_at`, `reference_date` | as in `opportunity_requirements` | The original proposal; an edited accept changes only the canonical requirement. CHECK: reference date iff `explicit_date` |
| `source_text` | varchar(500) | Evidence excerpt (the extractor caps it at 300 characters). Plain text |
| `extractor_name`, `extractor_version` | varchar | `requirements-rules`, `1` |
| `review_state` | enum `pending` / `accepted` / `rejected` | |
| `is_current` | boolean, default true | Whether the latest extraction of the current text proposed it. Pending ones that stop being proposed are deleted; reviewed ones stay with `false` |
| `accepted_requirement_id` | uuid FK → opportunity_requirements, null, SET NULL, indexed | The canonical requirement created on accept. CHECK: set only when `accepted` |
| `created_at`, `updated_at` | timestamptz | |

### `opportunity_source_records`

Each place an opportunity was seen. An opportunity can have many source records.

| Column | Type | Notes |
|---|---|---|
| `opportunity_id` | FK → `opportunities`, cascade | |
| `source_name` | varchar(100) | |
| `source_type` | enum `public_feed` / `ats` / `career_page` / `browser` / `manual` / `other` | |
| `external_id` | varchar(255), null | UNIQUE with `source_name`. NULLs don't collide |
| `source_url` | varchar(2048), null | |
| `raw_payload` | json, null | The original source item (≤ 256 KB), never altered by normalization. Replaced by the item's newest version when it changes. Never sent to the browser |
| `fetched_at`, `first_seen_at`, `last_seen_at` | timestamptz | CHECK: last ≥ first |
| `ingestion_source_id` | FK → `ingestion_sources`, null | Automated records only; NULL for manual provenance (Milestone 3) |
| `is_active` | boolean, default true | Present in the source's latest complete successful snapshot. CHECK: `is_active = (closed_at IS NULL)` |
| `closed_at` | timestamptz, null | When a complete successful snapshot no longer contained it. Cleared if it returns. Sync never deletes records |
| `source_published_at`, `source_updated_at` | timestamptz, null | The source's own dates, as stated |
| `content_hash` | varchar(64), null | SHA-256 of the normalized item including the raw payload: unchanged items skip every write except last-seen |

For automated records `source_name` is the source key (`community_feed:zshah-tech-internships`, `greenhouse:<board>`, `lever:<region>:<site>`), so `(source_name, external_id)` is unique per source. Index: `(ingestion_source_id, is_active)`.

An opportunity's **availability** is derived, not stored: `open` if any automated record is active, `closed` if it has automated records and none is active, `manual` if it has none.

### `opportunity_identifiers`

Deterministic identities shared across sources ([ADR-008 §6](decisions/ADR-008-opportunity-ingestion-and-deduplication.md#6-cross-source-identifiers)). Milestone 3.

| Column | Type | Notes |
|---|---|---|
| `opportunity_id` | FK → `opportunities`, cascade, indexed | |
| `namespace` | varchar(32) | `zshah`, `greenhouse`, `lever`, `url` |
| `value` | varchar(1024) | e.g. `examplerobotics:1001`, `global:examplesite:<uuid>`, a canonical URL |
| `created_at` | timestamptz | |

UNIQUE `(namespace, value)`: an identity belongs to exactly one opportunity, and identifiers never move. Only ingestion writes them; manual opportunities have none.

### `ingestion_sources`

The source registry. Safe configuration only: no URLs, no credentials. Milestone 3.

| Column | Type | Notes |
|---|---|---|
| `kind` | enum `community_feed` / `greenhouse` / `lever` | Picks the adapter and its hard-coded host |
| `identifier` | varchar(64) | Greenhouse board token, Lever site name, or the built-in feed's key |
| `region` | enum `global` / `eu`, null | CHECK: set exactly when `kind = 'lever'` |
| `display_name` | varchar(200) | Shown in the UI; the organization of opportunities imported from an ATS source |
| `enabled` | boolean, default true | Disabled sources are skipped by "sync all" and can't be synced individually |
| `scope` | enum `all` / `internships_only` | Milestone 4. New Greenhouse/Lever boards default to `internships_only` (title filter); CHECK `ck_ingestion_sources_builtin_scope_all`: the built-in feed is always `all`. Changing it clears `etag`/`last_modified` |
| `last_attempted_at`, `last_success_at` | timestamptz, null | `no_change` counts as a success |
| `etag`, `last_modified` | varchar, null | HTTP validators, stored only after a complete successful run |
| `created_at`, `updated_at` | timestamptz | |

UNIQUE `(kind, identifier, region)` with `NULLS NOT DISTINCT`. The migration seeds the built-in feed (`community_feed`, `zshah-tech-internships`, "Tech Internship Discovery Feed"). The API can't create `community_feed` rows or change any identifier.

### `ingestion_runs`

One sync of one source. Milestone 3.

| Column | Type | Notes |
|---|---|---|
| `source_id` | FK → `ingestion_sources`, cascade | Index `(source_id, started_at)`; partial UNIQUE `uq_ingestion_runs_one_running_per_source` on `(source_id)` WHERE `status = 'running'`: at most one running run per source, enforced by the database |
| `status` | enum `running` / `success` / `partial` / `failed` / `no_change` | A run still `running` after 15 minutes is marked `failed` by the next sync of that source |
| `started_at`, `finished_at` | timestamptz | |
| `source_generated_at` | timestamptz, null | The source's own snapshot time (the feed's `generated_at`) |
| `filtered_count` | int, default 0 | Milestone 4: provider items excluded by the source's scope. `fetched` = provider items, `filtered` = excluded, `normalized` = admitted to the pipeline |
| `fetched_count`, `normalized_count`, `created_count`, `updated_count`, `deduplicated_count`, `unchanged_count`, `closed_count`, `reactivated_count`, `invalid_count`, `error_count` | int, default 0 | |
| `error_summary` | varchar(500), null | Safe one-line reason for a failed run |

### `ingestion_run_errors`

Bounded, safe per-item problems: at most 100 stored per run; no stack traces, headers, credentials, or payloads. Milestone 3.

| Column | Type | Notes |
|---|---|---|
| `run_id` | FK → `ingestion_runs`, cascade, indexed | |
| `external_id` | varchar(255), null | The item's source ID, when known |
| `stage` | enum `fetch` / `validate` / `normalize` / `identify` / `persist` | |
| `code` | varchar(50) | e.g. `timeout`, `schema_mismatch`, `invalid_item`, `identity_conflict` |
| `message` | varchar(500) | |
| `created_at` | timestamptz | |

### `opportunity_requirements`

Structured hard requirements.

| Column | Type | Notes |
|---|---|---|
| `opportunity_id` | FK → `opportunities`, cascade | |
| `requirement_type` | enum `minimum_age` / `education` / `citizenship` / `work_authorization` / `other` | |
| `value` | json | Shape per type, below |
| `applies_at` | enum `application` / `program_start` / `explicit_date`, default `program_start` | Which date the requirement is evaluated on |
| `reference_date` | date, null | CHECK: set iff `applies_at = explicit_date` |
| `source_text` | text, null | Evidence from the posting |
| `extraction_method`, `extractor_name`, `extractor_version`, `confidence` | | Same provenance rules as `profile_facts` |
| `created_at`, `updated_at` | timestamptz | |

`value` shapes (validated by `app/opportunities/eligibility/schemas.py`):

| Type | Shape | Example |
|---|---|---|
| `minimum_age` | `{"years": int}` | `{"years": 16}` |
| `education` | `{"levels": [level, …], "accepts_incoming": bool}` | `{"levels": ["undergraduate"], "accepts_incoming": true}` |
| `citizenship` | `{"countries": [ISO alpha-2, …]}` | `{"countries": ["US"]}` |
| `work_authorization`, `other` | free-form object; the UI writes `{"description": str}` | not evaluated by v1 (`needs_verification`) |

### `opportunity_evaluations`

One evaluation (eligibility and, since Milestone 4, fit) of an opportunity for a profile. Rows are **history**: re-evaluating adds a row. The latest `evaluated_at` is current (`app.repositories.latest_evaluation`; equal timestamps are broken by `id`, which is stable but not chronological).

| Column | Type | Notes |
|---|---|---|
| `profile_id` | FK → `profiles`, cascade | |
| `opportunity_id` | FK → `opportunities`, cascade | |
| `eligibility_status` | enum `eligible` / `needs_verification` / `ineligible` | |
| `eligibility_rules_version` | varchar(20) | e.g. `v1` |
| `depends_on_projected_status` | boolean | True only when the final status depends on projected-status rule results (not merely that one was evaluated); see [eligibility.md](eligibility.md#time-aware-evaluation) |
| `evaluated_at` | timestamptz | |
| `input_fingerprint` | varchar(64), null | SHA-256 of the canonical eligibility inputs ([ADR-008 §9](decisions/ADR-008-opportunity-ingestion-and-deduplication.md#9-evaluation-without-history-explosion)). Automatic evaluation skips when the latest evaluation has the same fingerprint. NULL for evaluations made before Milestone 3 (Milestone 3) |

| `fit_score` | int, null | 0–100 (CHECK). Milestone 4 |
| `score_breakdown` | json, null | Components, reasons, evidence, coverage ([scoring.md](scoring.md#coverage-and-breakdown)); plain data, no HTML |
| `scoring_version` | varchar(20), null | e.g. `v1` |
| `fit_input_fingerprint` | varchar(64), null | SHA-256 of the fit inputs (CHECK length 64). Automatic evaluation appends a row only when this or `input_fingerprint` changed |

Index: `ix_opportunity_evaluations_pair_evaluated_at` (`profile_id`, `opportunity_id`, `evaluated_at`). CHECK `ck_opportunity_evaluations_fit_fields_together`: the four fit columns are all NULL (evaluations from before Milestone 4) or all set.

### `eligibility_rule_results`

The explanation of an evaluation: one ELIG-REQ-000 row for the requirement assessment (`requirement_id` null), then one row per evaluated requirement.

| Column | Type | Notes |
|---|---|---|
| `evaluation_id` | FK → `opportunity_evaluations`, cascade | |
| `requirement_id` | FK → `opportunity_requirements`, SET NULL, null | |
| `position` | int | Order within the evaluation |
| `rule_id` | varchar(50) | e.g. `ELIG-EDU-001` |
| `status` | enum (as above) | |
| `reason` | text | Human-readable explanation |
| `reference_date` | date, null | The date the rule evaluated |
| `depends_on_projected_status` | boolean | |
| `details` | json, null | Structured inputs/outputs (e.g. age, projected phase) |

### `auth_users`

The single owner account ([ADR-007](decisions/ADR-007-single-user-auth-and-private-api.md)). Created only by `python -m app.cli create-owner`; there is no registration endpoint.

| Column | Type | Notes |
|---|---|---|
| `username` | varchar(64), UNIQUE | 3–64 of letters, digits, `_`, `.`, `-` (CLI-validated) |
| `password_hash` | varchar(255) | Argon2id PHC string (pwdlib). Never the password |
| `is_active` | boolean, default true | Inactive users can't log in, and their sessions stop working |
| `created_at`, `updated_at` | timestamptz | |

No email, name, or phone.

### `auth_sessions`

Server-side login sessions. The browser holds the opaque random token (cookie `if_session`); the database stores only its SHA-256.

| Column | Type | Notes |
|---|---|---|
| `user_id` | FK → `auth_users`, cascade | Indexed |
| `token_hash` | varchar(64), UNIQUE | `sha256(token)` hex. The raw token is never stored |
| `created_at` | timestamptz | |
| `expires_at` | timestamptz | Absolute expiry (`SESSION_TTL_HOURS`) |

Logout deletes the row. Login deletes the user's expired sessions and the browser's previous session. `set-password` deletes all of the user's sessions. The CSRF token is derived from the session token (HMAC), so it isn't stored.

### `applications`

The owner's application tracking. Private runtime data; never read by eligibility.

| Column | Type | Notes |
|---|---|---|
| `opportunity_id` | FK → `opportunities`, cascade, UNIQUE | Single-user: at most one tracking row per opportunity (the "profile + opportunity" pair, since there is one profile) |
| `status` | enum `saved` / `applying` / `applied` / `interview` / `offer` / `accepted` / `rejected` / `withdrawn` | Any status may follow any other (no transition rules) |
| `submitted_on` | date, null | When the application was submitted |
| `notes` | text, null | Private notes |
| `created_at`, `updated_at` | timestamptz | |

## Not Yet Modeled

- Transcript and course-list uploads, DOCX, OCR, and AI extraction (only text and text-based PDF résumés in Milestone 5)

## Provenance Rules

- Stored artifacts are never modified. Re-parsing replaces only the source's `pending` facts and never recreates a candidate the owner already accepted or rejected.
- Every `profile_facts` row records its source kind and extraction method. AI-inferred and parsed facts name the extractor and start `pending` and unverified; only `accepted` facts reach fit scoring.
- Hard eligibility reads only canonical `profiles` columns.

Design rules from [ENGINEERING_GUIDELINES.md §6](../ENGINEERING_GUIDELINES.md#6-database-standards) apply. Authorization is enforced in the FastAPI backend by one dependency on every private route ([ADR-007](decisions/ADR-007-single-user-auth-and-private-api.md)).

## How the Private API Writes

- The API keeps exactly one `profiles` row (created by the first `PUT /api/profile`).
- A manually created opportunity always gets one `opportunity_source_records` row: `source_type = manual`, `source_name = manual`, no `external_id`, no raw payload. It's curated from creation (`manually_curated_at`).
- Requirement rows written by the API have `extraction_method = manual`. An opportunity update replaces the complete requirement set: old rows are deleted, and past `eligibility_rule_results` keep their text with `requirement_id` set to NULL. Any update (including of an imported opportunity) sets `manually_curated_at`.
- Opportunity create/update appends an `opportunity_evaluations` row when a profile exists **and** the eligibility or fit inputs changed (fingerprints). An eligibility-relevant profile change or any Match Profile save runs one catalog pass that appends rows only for opportunities whose inputs changed, and `POST /api/opportunities/{id}/evaluate` always appends. Nothing is overwritten.
- `PUT /api/profile/match` creates the profile row if needed, sets the fit preference columns, and replaces the Match Profile facts (unchanged facts aren't rewritten), all in one transaction with the catalog pass.
- Profile source uploads ([ADR-011](decisions/ADR-011-profile-source-ingestion-and-review.md)) write the source, its artifact, and pending facts in one transaction, with no catalog pass. A review batch updates facts and runs at most one catalog pass, only when an accepted fit fact changed. Deleting a source deletes its artifact and facts by cascade (manual facts have no `profile_source_id` and are untouched), with one catalog pass if it had accepted fit facts.

## How Ingestion Writes

Only `app/ingestion/pipeline.py` writes imported data ([ADR-008](decisions/ADR-008-opportunity-ingestion-and-deduplication.md)):

- Items a source's `internships_only` scope excludes are counted in `filtered_count` and never processed (so a complete run closes records they created earlier).
- A new item creates an `opportunities` row (`unassessed`, no requirements), one automated `opportunity_source_records` row, its unclaimed `opportunity_identifiers`, and (with a profile) one evaluation.
- An item matching another source's opportunity by identifier adds only a source record (and any unclaimed identifiers).
- A changed item updates its source record, and the canonical fields only when the opportunity isn't curated. An unchanged item only moves `last_seen_at`/`fetched_at` (one bulk statement per run).
- A complete successful run closes the source's active records it didn't contain. Nothing is deleted.

## Keeping This File in Sync

- Every migration that changes the schema must update this file in the same change.
- Migrations are the source of truth. If this file and the migrations disagree, the migrations win and this file is a bug. CI's `alembic check` and `tests/test_migrations.py` fail if the ORM models drift from the migrations.
