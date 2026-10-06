# ADR-025: Home Dashboard and Application Engine v2

Status: Accepted (Milestone 15, on the feature branch; subject to owner review)

Date: 2026-10-06

## Context

The Action Inbox ([ADR-020](ADR-020-action-inbox.md)) answers "what needs me today", but the app has no overview (how is the pipeline doing, what is coming up, is discovery healthy) and application tracking is a single editable row: nothing records *when* an application was submitted or what changed, so there is no honest way to say how long employers take to answer. This ADR adds a read-only home dashboard and extends the existing application states with a small history. It adds no competing state machine: the eight statuses (`saved`, `applying`, `applied`, `interview`, `offer`, `accepted`, `rejected`, `withdrawn`), `next_action`, `next_action_due` and `interview_at` stay exactly as they are.

## Decision

### 1. One additive migration (`c9e2b7a4d1f8`, after `a3c7e9b1d5f2`)

- `applications.applied_at` (timestamptz, nullable).
- `application_events` (append-only): `id` uuid, `application_id` FK to `applications` ON DELETE CASCADE (indexed), `event_type`, `occurred_at` timestamptz, `from_status`, `to_status` (nullable, the existing status values), `metadata_json` JSONB (NOT NULL, CHECK `length(metadata_json::text) <= 2000`), `created_at`.
- Event types (VARCHAR + CHECK, like every enum here): `created`, `status_changed`, `next_action_changed`, `interview_scheduled`, `interview_updated`, `note_added`, `deadline_changed`, `offer_received`.

The old backend runs unchanged on the migrated schema (a nullable column it never reads and a table it never writes). **Downgrade** drops the table and the column (history and `applied_at` are lost; applications are kept).

### 2. History is written in the same transaction, on meaningful changes only

`app.services.applications.save_application` (called by the existing `PUT /api/opportunities/{id}/application`) compares the stored row with the incoming fields and appends events in the caller's transaction, so an event exists if and only if its change committed. A PUT that changes nothing writes nothing; `submitted_on` edits are not events.

| Change | Event |
|---|---|
| Row created | `created` (`to_status`) |
| Status differs | `status_changed` (`from_status`, `to_status`) |
| Status becomes `offer` (including creation) | additionally `offer_received` |
| `next_action` text differs | `next_action_changed` (`{"next_action": ...}`) |
| `next_action_due` differs | `deadline_changed` (`{"from", "to"}`; "deadline" here means the follow-up date, not the posting's application deadline) |
| `interview_at` set from empty | `interview_scheduled` (`{"from","to"}`) |
| `interview_at` changed or cleared | `interview_updated` |
| `notes` changed to a non-empty value | `note_added` (`{"length"}` only: private note text is never copied into history) |

Events written together get microsecond-offset `occurred_at` values so their order is deterministic. `interview_at` keeps only the latest interview on the row; a second round is a second `interview_updated`/`interview_scheduled` event, so multiple interviews survive in history.

**No fabricated history.** Applications that existed before this migration have no events and no `applied_at`; nothing is back-filled. Their timeline starts at the first change after deployment (no `created` event, because they were not created then). The detail page says so. Deleting an application deletes its events (cascade).

### 3. `applied_at`

Set to the server's `now` the first time the status becomes `applied` while `applied_at` is empty. The owner can correct it (the field is accepted by the same PUT, bounded 2000-2999) and a manual value is never overwritten, including when an application moves away from and back to `applied`. It is a timestamptz so it can be compared with event times; it is not set when an application skips `applied` entirely. `started_at` for `applying` was not added: nothing needs it. No compensation field was added.

### 4. Transitions stay permissive

Any status may follow any other, as before. Real processes skip stages (a rolling-admission program may go `applying` to `accepted`), reopen after a rejection, or need a correction, and the owner is the only user: a rule that blocks an honest correction is worse than a rule that lets a typo through. The quick actions *offer* sensible next steps (for example Mark offer is not shown on `saved`), but the stage selector reaches any status. Nothing is stored for "overdue": it is derived on read (`next_action_due < today` and status not `accepted`/`rejected`/`withdrawn`). A follow-up due today is due, not overdue.

### 5. `GET /api/applications` and `GET /api/applications/{id}/events`

- List/pipeline (owner-only, reuses nothing new in the data model): `stage` (repeatable), `company` (substring, escaped), `due_soon` (due within 3 days, inclusive of today), `follow_up_overdue`, `interview_upcoming` (from today), `sort` (`next_action` default, `newest`, `applied`, `interview`, `company`, `stage`), `limit` (max 200), `offset`, `today`. One statement plus a count window; items carry the opportunity's title, organization and link and the derived `follow_up_overdue`. It lists every tracked application, hidden opportunity or not (this is the owner's workspace).
- Events: oldest first; 404 for an unknown application, an empty list for a legacy one. `ApplicationResponse` gains `id`, `opportunity_id` and `applied_at` (additive).

### 6. `GET /api/dashboard`

One owner-only, read-only, composed response, in a constant number of statements (18 with a profile present; a test inserts more data and asserts the same count). It reuses the Action Inbox's section queries (closing soon, pending review, applications needing attention, program verify-by) and source coverage / the data-age check rather than re-deriving them, so the numbers match the pages they link to. `InboxItem` gains an optional `kind` (`follow_up_overdue`, `follow_up_due`, `interview`, `stale`) so the dashboard can label application actions. The Inbox's stale rule is parameterised: the Inbox keeps `saved`/`applying` (ADR-020); the dashboard uses `applying`/`applied` for the same 14 days.

| Part | Rule |
|---|---|
| `actions` | closing soon (14 d), suggested requirements awaiting review, applications (follow-up due within 3 d or overdue, interview within 7 d, stale applying/applied 14 d) with `total`; at most 10 items per section |
| `pipeline` | count per status, all eight keys always present |
| `high_fit_new` | not hidden, open, first found within 7 days, eligible or needs_verification, fit at least 70, **no application row at all** (stricter than "not applied": anything already tracked is already being handled), eligible before needs_verification, then fit; 5 items |
| `upcoming` | deadlines (14 d), verify-by dates, follow-ups and interviews (14 d), chronological, 8 items; hidden excluded; interviews carry the instant |
| `discovery` | open, direct-source-backed, independent %, description %, feed-only, newest successful sync, sources warning/stale/failing |
| `requirements` | counts of suggestions pending / accepted / rejected (called suggestions awaiting review, never problems) |
| `funnel` | applied, interviewed, offered, accepted, rejected/withdrawn before interview; rates and medians below |

**Funnel semantics.** An application counts as having *reached* a stage from its current status, its timestamps, or its recorded history (`to_status`/`offer_received`/`interview_scheduled` events), so one that was rejected after an interview still counts as interviewed. Rates (applied to interview, interview to offer, offer to accepted) are returned only when the denominator is at least 5 (`MIN_RATE_DENOMINATOR`), otherwise `null`; never NaN or a fake 0. Median days from `applied_at` to the first interview / rejection / offer event are returned only when at least 3 applications have both (`MIN_MEDIAN_SAMPLES`), otherwise `null`. Because events begin at deployment, medians only become available as new applications accumulate; the UI says "Not enough data yet". Rates are over all tracked applications (hidden opportunities included), because they describe the owner's process, not the catalog.

### 7. Time zones

Day-only fields (`next_action_due`, `application_deadline`, `submitted_on`, `verify_by`) are plain dates compared with a `today` date. The browser sends its local date as `today` (default: the server's UTC date), exactly like the list's `today` (ADR-012 §14). `interview_at`, `applied_at` and event times are timestamptz instants; the browser renders them in its own zone and sends `datetime-local` input as an instant. Backend "within N days" windows for interviews are half-open UTC ranges from midnight of `today` (as in ADR-020), so an evening interview in a far-west zone can fall in the next UTC day's window; accepted.

### 8. UI

- `/dashboard` is the default authenticated route (the `*` fallback and the post-login redirect default; `/login` is untouched, `/` is left to the landing page work). Sections: greeting and system health, Action required (largest), Application pipeline (a segmented bar on desktop, a list on mobile; "by current status", no implied order), New high-fit, Upcoming, Discovery health (links to `/sources`), Requirement health (links to `/requirements`), Outcomes. Restrained: type and thin dividers inside one bordered panel, 8-12 px radii, existing Tailwind tokens.
- `/applications` is the workspace: List and Pipeline views (Saved, Applying, Applied, Interview, Offer, Outcome), filters and sorts, and quick actions (Start application, Mark applied, Schedule follow-up, Add interview, Mark offer, Accept, Reject, Withdraw, Open application link). Stage changes use an accessible `<select>`, not drag-and-drop; mobile shows one stage at a time as tabs. The application detail shows the History timeline and an editable **Applied at**.
- Copy states the roles subtly: Dashboard is the overview, Inbox the action queue, Applications the workspace.

## Consequences

- Positive: an overview from existing data, durable and honest outcome history from now on, one extra table, no new service, no new dependency.
- Negative: history and medians start empty for existing applications. `interview_at` still holds one value on the row. The dashboard reads the clock from the browser's `today`, so two devices in different zones can disagree near midnight. The pipeline grid is cramped at tablet width (it scrolls into stage tabs on mobile).
- Rollback: the migration is additive; rolling the app back without a downgrade leaves the column and table unused. `alembic downgrade a3c7e9b1d5f2` drops them (history lost).
- Not built: editing or deleting individual events, reminders or notifications, compensation, `started_at`, stricter transitions, drag-and-drop, saved filters, charts beyond the bar.
