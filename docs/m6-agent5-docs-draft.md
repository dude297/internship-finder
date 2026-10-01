# Milestone 6, Agent 5 — docs draft (Ashby + opportunity type classification)

Not wired into `docs/sources.md` yet; this is the text to merge there, plus a note on the
classification change. Agent 5 (Ashby adapter + classification) was told not to edit docs
directly — hand this to whoever integrates the Milestone 6 docs pass.

## For `docs/sources.md` — Source Review and Attribution table

Add a row:

| Source | Role | API / docs | License / usage basis | Attribution | Implemented? | Notes |
|---|---|---|---|---|---|---|
| Ashby Job Postings API | Direct ATS (layer 2), per-company hosted job boards | `GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=false` ([docs](https://developers.ashbyhq.com/docs/public-job-posting-api)) | Public GET endpoint, no authentication, intended for publishing a company's hosted job board | The configured organization name; original posting link (`jobUrl`) kept | **Yes** (Milestone 6) | Listed (`isListed: true`) postings only. The authenticated `job.list`/`jobPosting.list` API and application submission are never used |

Move the "Ashby" row out of **Planned Sources** (it's currently listed there as "Planned"; remove
that row once this ships).

## For `docs/sources.md` — new "Ashby boards" section (after "Lever sites")

### Ashby boards

- **Source name / key:** `ashby:<board name>`; added on the Sources page from a hosted board
  link (`https://jobs.ashbyhq.com/<board>`) or a bare board name
- **Board names:** verified against the live public endpoint
  (`api.ashbyhq.com/posting-api/job-board/{name}`) that board names are **case-insensitive at the
  provider** — `Ashby`, `ASHBY`, and `aShBy` all resolve the same hosted board — though the
  `jobUrl` Ashby returns keeps the owner's original casing. We therefore lowercase and store the
  board name, exactly like the Greenhouse board token and the Lever site slug, and duplicate
  detection is an exact match on that lowercased value (so `ExampleBoard` and `exampleboard`
  collide, same as Greenhouse/Lever). Ashby's docs don't document an explicit character-set
  grammar for board names; we validate with the same slug pattern already used for Greenhouse and
  Lever (`^[a-z0-9][a-z0-9_.-]{0,63}$` after lowercasing), which covers every board name we've
  observed and rejects anything that isn't a plain path segment
- **Stable ID:** the job `id` (a UUID); identity `ashby:<board>:<id>` plus the canonical `jobUrl`
- **Mapped:** `title`, the configured organization name, `descriptionPlain` when present else
  `descriptionHtml` → plain text, `location` + `secondaryLocations[].location` joined with " · ",
  `jobUrl` as the application URL (falling back to `applyUrl` if `jobUrl` is absent — `jobUrl` is
  the posting page itself, which is what the owner wants to open and read first; `applyUrl` jumps
  straight to the application form), `workplaceType` (`OnSite`/`Remote`/`Hybrid`, case-insensitive)
  or, only when `workplaceType` is absent, `isRemote: true` → remote (`isRemote: false` is never
  taken to mean on-site, matching the existing Lever/feed convention), `publishedAt` → posted date,
  and `employmentType == "Intern"` → internship (otherwise the shared title matcher decides, see
  below). `department`, `team`, `address`, and `compensation` (never requested — we always pass
  `includeCompensation=false`) stay out of scope / in the raw payload only
- **Listed postings only:** Ashby's public endpoint includes an `isListed` boolean per job
  ("Should this job be listed in the list of postings on your job board"). Unlisted jobs
  (`isListed: false`) are excluded **before** normalization, so they're never imported and never
  count as a provider item — this is a different mechanism from the `internships_only` scope
  filter (which runs on title and does show up in the run's `filtered_count`); an Ashby posting
  that becomes unlisted simply disappears from the snapshot the same way a removed posting does,
  and a complete successful sync closes it through the normal closure rule. If `isListed` is ever
  absent from a job object (not observed in practice — every job on the live public endpoint we
  checked included it), it's treated as listed rather than silently dropped, since dropping on an
  unexpected shape would be a worse failure mode than importing one extra posting
- **Scope:** **Internships only** by default (title filter, below); **All postings** imports
  every listed posting
- **SSRF boundary:** only `api.ashbyhq.com` is added to the fetch allowlist (`ALLOWED_HOSTS`); the
  hosted board host `jobs.ashbyhq.com` is recognized only when parsing a board reference out of a
  pasted URL and is never itself requested. The authenticated Ashby API is a different host
  entirely and is never used
- **Completeness check:** none needed — the public endpoint has no top-level `count`/`total`
  field to cross-check (unlike Greenhouse's `meta.total` or the discovery feed's `count`)

Also add Ashby to the "Board scope: internships only" section's heading (it currently says
"Greenhouse and Lever" — Ashby should be included there too, since it has the same
default-scope / filtered_count behavior) and to "Common Behavior → Network safety" (currently
"the four allowlisted API hosts" → five, once Ashby ships).

## Opportunity type classification (ADR-012 §13)

New shared function `classify_opportunity_type(title, *, structured_intern=None)` in
`backend/app/ingestion/normalize.py`, used by every adapter instead of each adapter doing its own
thing:

1. A structured provider signal that says "intern" wins: Lever `categories.commitment` containing
   "intern", Ashby `employmentType == "Intern"`, the discovery feed's `program == "Internship"`.
2. Otherwise the existing whole-word title matcher (`is_internship_title`, unchanged) decides.
3. Otherwise `other`.

**Behavior change and its consequence:** previously, Greenhouse never classified by title at all
(every Greenhouse posting was `other` unless a future classifier ran), Lever used its structured
`commitment` field only, and the feed used its `program` field only. Now title is a fallback for
all three. Concretely: a Greenhouse posting titled "... Intern" is now `internship` instead of
`other`; a Lever posting titled "... Internship" but with a non-"intern" (or blank) `commitment`
is now `internship` instead of `other`; same for the feed's `program` field. This changes the
normalized item's content hash for every existing imported posting whose title matches, so the
**first sync after this release reports those postings as "updated" once** (title/org/etc. are
unchanged; only `opportunity_type` moves). This is expected and one-time — not a bug, not data
loss (nothing is deleted or closed by it).

Confirmed unchanged: `is_internship_title` itself wasn't touched. Broad words ("student",
"junior", "entry-level", "new grad") still don't match and classify as `other`; tests added in
`tests/test_ingestion_unit.py` (`test_classify_opportunity_type_*`) cover the structured-wins and
title-fallback paths, and each adapter has a title-fallback test
(`test_greenhouse_non_intern_title_is_other`,
`test_lever_falls_back_to_title_when_commitment_isnt_structured_intern`,
`test_feed_falls_back_to_title_when_program_isnt_structured_intern`,
`test_ashby_falls_back_to_title_when_employment_type_isnt_structured_intern`).

Type is a discovery/display aid, never eligibility — unchanged by this.
