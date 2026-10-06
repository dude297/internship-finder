# ADR-020: Action Inbox and Application Follow-Up

Status: Accepted (Milestone 10, on the feature branch; subject to owner review)

Date: 2026-10-06

## Context

The app finds and scores opportunities, but the owner has to open several pages to learn what needs doing today: a deadline closing, a high-fit posting that just appeared, suggestions waiting for review, a failing source, a program whose dates need re-checking, a follow-up they promised themselves. Application tracking ([ADR-007](ADR-007-single-user-auth-and-private-api.md), `applications`) records status, submit date and notes but has no notion of "what next, and by when".

This is a personal tool, not a CRM: the goal is one small page of things to act on, not pipelines, reminders by email, or analytics.

## Decision

### 1. Three nullable follow-up columns on `applications`

`next_action` (varchar(200)), `next_action_due` (date), `interview_at` (timestamptz). One additive migration (`a3c7e9b1d5f2`, after `d4f8a1c6e2b9`); no data change; downgrade drops the columns. They ride on the existing `PUT /api/opportunities/{id}/application` (which, like `notes`, replaces the whole record: omitted fields are cleared) and the existing tracking form. Private runtime data; never read by eligibility or fit. No status history: the app does not need one yet (`updated_at` is the only "last touched" signal, and it is what the stale rule uses).

### 2. `GET /api/inbox` is read-only, owner-only, derived on read

Behind the existing `require_owner` boundary. Nothing is stored or changed. The response is six sections `{total, items}`; every item is minimal (`id`, `title`, `organization`, `reason`, optional `date`). Each section returns at most **10** items and the full `total`. Hidden opportunities ([ADR-017](ADR-017-owner-opportunity-decisions.md)) are excluded from every section.

| Section | Rule |
|---|---|
| `new_high_fit` | Open, first found (`first_seen_at`, never the provider's posted date) within 7 days, the current profile's latest fit score **>= 70**; highest fit first, ties newest posted. Empty without a profile. |
| `closing_soon` | Open, `application_deadline` (a verified date only, [ADR-014](ADR-014-structured-source-expansion-and-program-registry.md) §6) from today to today + 14 days, soonest first. |
| `pending_requirement_review` | Open opportunities with pending requirement candidates ([ADR-012](ADR-012-opportunity-requirement-intelligence-and-automation.md)): count of such opportunities plus the ones with the most suggestions. Display only; it never accepts a suggestion or changes eligibility. |
| `source_warnings` | Sources whose derived health ([ADR-012](ADR-012-opportunity-requirement-intelligence-and-automation.md) §11) is `warning`, `stale` or `failing`. Disabled and never-run sources are not warnings. `id` is the source ID; items link to the Sources page. |
| `program_verify_by` | Registry-backed (active curated-registry record) opportunities whose `verify_by` has passed or falls within 14 days, soonest first. |
| `applications` | Tracked, not accepted/rejected/withdrawn: `next_action_due` overdue or within 3 days; or `interview_at` from the start of today to the end of the 7th day ahead; or status `saved`/`applying` with no update for more than 14 days. One reason per item (due, then interview, then stale), ordered by the soonest due/interview date, stale last. |

"Open" is the list's availability rule (an active automated record, or managed by hand), shared as `discovery.is_open`. Tracked applications are not required to be open: a follow-up on a posting that closed still matters.

The thresholds (70, 7, 14, 14, 3, 7, 14, limit 10) are named constants in `services/inbox.py`. Fit has no official bands ([scoring.md](../scoring.md)); 70 is a deliberate "worth a look" cut that the owner can change in one place.

### 3. Set-based, constant statements

One statement per section (window `count() OVER ()` gives `total` with the bounded rows), plus the profile lookup and the two source-health queries already used by freshness. The count does not grow with the catalog; `tests/test_inbox.py` asserts it stays equal when rows are added and that every section is capped.

### 4. One clock

`build_inbox(db, today=None, now=None)` reads the server's UTC date once. `GET /api/inbox?today=YYYY-MM-DD` (bounded 2000-2999, like the list's `today`) exists so tests pin the date. Date-time windows use UTC midnights.

### 5. UI

An **Inbox** page at `/inbox` and a nav item. The post-login landing page stays `/opportunities` (changing it would change established e2e and login expectations); the nav item is first. Each section has an explicit empty state and links to the opportunity (or `/sources`), plus an "all" link into the filtered list when more exist than shown. The tracking form gains Next action, Next action due and Interview at.

## Consequences

- Positive: one place to start the day; no new tables; no sync, eligibility or fit change.
- Negative: the stale rule uses `updated_at`, so any edit (even a notes typo) resets it. Interview times are compared in UTC windows, so an interview late in the evening local time can land on the next UTC day in the reason text. No push, email or calendar integration.
- Rollback: the columns are additive; rolling the app back without a downgrade ignores them. Downgrading deletes follow-up fields.
- Not built: status history, snooze/dismiss of inbox items, per-section configuration, notifications.
