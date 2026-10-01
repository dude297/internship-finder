## Amendment (2026-10-01): Scheduled source sync (Milestone 6)

ADR-009 §11 said source sync stays manual and no scheduled cloud sync is enabled. ADR-012 §10
reopens that: a GitHub Actions workflow (`.github/workflows/sync-production.yml`) now syncs every
enabled production source twice a day (06:17 and 18:17 America/Los_Angeles) and on manual
`workflow_dispatch`, by running `python -m app.cli sync-sources --scheduled` — the same CLI the
owner already uses by hand, calling the same pipeline the API uses.

**Connects directly to Neon, not through Render.** The workflow talks straight to the Neon
`DATABASE_URL`, the same way a trusted local shell does for migrations (ADR-009 §10). It never
calls the Render API or the Render URL, so it doesn't keep the free instance awake and adds no
new path to the FastAPI service. Render's cold starts (ADR-009 §8, §Consequences) are unaffected;
the first browser request after a scheduled sync still waits for Render to wake, same as today.

**No paid service.** GitHub Actions on a public repository is free, with no payment method on
file (ADR-009 §2's zero-cost rule). The job is bounded (`timeout-minutes: 20`) and runs at most
twice a day plus occasional manual dispatches, well inside the free public-repo minutes GitHub
Actions already doesn't meter.

**The secret.** `PRODUCTION_DATABASE_URL` is a GitHub **environment** secret on an environment
named `production`, not a repository secret — scoped so only a workflow run that explicitly
targets that environment can read it, and so protection rules (required reviewers, wait timers)
can be added later without a code change. It is set only on the one step that needs it
(`DATABASE_URL: ${{ secrets.PRODUCTION_DATABASE_URL }}`), never at the job or workflow level, and
is never echoed, logged, or passed as a command-line argument.

**The per-source running-run constraint is still the authoritative concurrency guard.** The
workflow's `concurrency: { group: production-source-sync, cancel-in-progress: false }` only
prevents GitHub from queuing two overlapping scheduled runs of *this workflow*; it is not what
keeps two syncs of the same source from running at once. That guard is, and remains, the
database's partial unique index on `ingestion_runs (source_id) WHERE status = 'running'`
(ADR-008 §4) plus the pipeline's `SyncInProgress` check — the same mechanism that already
protects the manual Sources-page and CLI paths from each other. A scheduled run and a manual
sync racing each other are resolved the same way two manual syncs are: one wins the index, the
other is skipped and reported as such.

**Inactivity auto-disable.** GitHub automatically disables a public repository's scheduled
workflows after 60 days with no repository activity (commits, issues, PRs — anything, not
specifically to this workflow). This repository is under active development, so it isn't
expected to go quiet for 60 days, but if it ever does, the schedule silently stops firing.
`workflow_dispatch` on the Actions tab still works to re-enable it (GitHub re-enables a disabled
scheduled workflow on its next manual dispatch, or it can be re-enabled explicitly from the
workflow's "..." menu), and is also the owner's way to run a sync on demand without waiting for
the next scheduled slot, or to catch up after exactly this kind of auto-disable.

**DST.** The workflow uses the `schedule.timezone` key (an IANA zone string, supported by GitHub
Actions as of 2024) rather than a UTC cron expression, so 06:17/18:17 America/Los_Angeles is
resolved to the correct UTC offset per run and the twice-yearly PDT/PST transition needs no
manual edit. (If `timezone` were ever unsupported or unreliable, the fallback is a UTC cron,
e.g. `17 13,1 * * *` for PDT — which would drift by an hour for part of the year until manually
adjusted for PST; that fallback is not currently needed.)

**The fork/PR secret boundary.** `schedule` and `workflow_dispatch` events only ever run using
the workflow file on the repository's own default branch, and GitHub Actions never runs a
*fork's* `schedule` event at all (only the upstream repository's schedule fires, and only against
upstream's default-branch code) — so a pull request, including one from a fork, can neither
trigger this workflow nor see `secrets.PRODUCTION_DATABASE_URL`, regardless of what workflow YAML
the PR itself contains. This workflow deliberately excludes `pull_request`, `pull_request_target`,
and `push` triggers so that remains true by construction, not only by GitHub's default behavior,
and the job also re-checks `github.repository == 'dude297/internship-finder' && github.ref ==
'refs/heads/main'` as defense in depth against a manual dispatch run from the wrong ref.
