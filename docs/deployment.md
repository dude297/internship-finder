# Deployment

Hosted architecture: [ADR-009](decisions/ADR-009-hosted-deployment-architecture.md). This file is the runbook. It never contains secrets: no `DATABASE_URL`, proxy secret, password, hash, session or CSRF token.

## Status

| Part | State |
|---|---|
| Neon | **Provisioned.** Project `sweet-dew-33937746`, PostgreSQL 18, `aws-us-west-2`, database `internship_finder`. Owner created once (CLI, `getpass`). |
| Render | **Deployed.** `internship-finder-api` (`srv-dastve60tbcc7392dfgg`), the only Render service. Auto-deploy off, branch `main`. |
| Vercel | **Deployed.** Project `internship-finder`, production alias `internship-finder-pi.vercel.app`; Git deployments off (CLI deploys only). |
| Scheduled sync | **Active.** GitHub environment `production` (deployment branches: `main` only) with secret `PRODUCTION_DATABASE_URL` (Neon pooled URL). |

The released milestone, production `main` SHA, and schema revision are in the generated status block of [PROJECT_STATE.md](../PROJECT_STATE.md) (source: [`docs/status.json`](status.json)). Each release's deploy IDs, smoke results, and counts are in its immutable record under [`docs/releases/`](releases/).

## Topology

```text
Browser ──HTTPS──► https://internship-finder-pi.vercel.app   (Vercel Hobby, project "internship-finder")
                     ├─ static Vite build (SPA fallback to index.html)
                     └─ /api, /api/* ──► https://internship-finder-api-eld4.onrender.com/api/*
                                          adds X-IF-Proxy-Secret (Production env only)
                                          (Render Free "internship-finder-api", Oregon, 1 instance, 1 worker)
                                               └─► Neon Free project sweet-dew-33937746, aws-us-west-2,
                                                   PostgreSQL 18, database internship_finder, direct endpoint
```

The only public app URL is the Vercel production alias. The browser never calls `onrender.com`. The Render URL answers directly, but only public endpoints work without a session, and direct login attempts share one throttle bucket.

## Cost Constraint

$0/month, no payment method, no automatic billing or upgrade ([ADR-009 §2](decisions/ADR-009-hosted-deployment-architecture.md#2-zero-cost-rule-permanent)). All three services are on free plans with no card: Vercel Hobby (owner-confirmed 2026-09-28), Render Free, Neon Free. If any platform asks for payment information, stop that path and write a new ADR.

## Configuration

### Render (`internship-finder-api`)

| Setting | Value |
|---|---|
| Plan / region / instances | Free / Oregon / 1 |
| Root directory | `backend` |
| Build | `pip install .` (recommended, owner action pending: `pip install -r requirements.lock && pip install --no-deps .`, the same locked install CI uses; [development.md](development.md#dependency-lock)) |
| Start | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (one worker; don't add `--workers`) |
| Health check | `/api/health` |
| Auto-deploy / PR previews | Off / off |

Environment variables (names only; values live in Render):

| Variable | Value |
|---|---|
| `DATABASE_URL` | Secret. Neon **direct** connection string (`neonctl connection-string`), as Neon prints it (`postgresql://…?sslmode=require…`); the app switches the driver |
| `SESSION_COOKIE_SECURE` | `true` |
| `SESSION_TTL_HOURS` | `24` |
| `PYTHON_VERSION` | `3.12` |
| `HOSTED` | `true` |
| `PROXY_SHARED_SECRET` | Secret. Random, ≥ 32 characters, identical to Vercel's |

Never set `INGESTION_FIXTURE_FILE`.

### Vercel (`internship-finder`, team `dude297s-projects`)

| Setting | Value |
|---|---|
| Plan | Hobby |
| Root directory / framework | `frontend` / Vite |
| Install / build / output | `npm ci` / `npm run build` / `dist` (also in `frontend/vercel.json`) |
| Node | 24.x |
| Git deployments | Disabled by `frontend/vercel.json` (`git.deploymentEnabled: false`); the project is connected to GitHub, but pushes and pull requests create no deployments |
| Deployment Protection | Standard (Vercel Authentication on everything except the production alias) |
| Production alias | `internship-finder-pi.vercel.app` |

Environment variables: **only** `PROXY_SHARED_SECRET`, type Sensitive, **Production** only. Nothing `VITE_*`, no API base URL, no database credentials. The `/api` route in `vercel.json` sends it as `X-IF-Proxy-Secret`, sets `Cache-Control: no-store`, and runs before the SPA fallback.

### Proxy secret

- Generate: `python -c "import secrets; print(secrets.token_urlsafe(48), end='')" > <file outside the repo>`.
- Set it from that file without displaying it: Render (API or dashboard) and `vercel env add PROXY_SHARED_SECRET production --sensitive --yes < <file>`. Delete the file afterwards.
- Rotate: set the new value in both places, redeploy Render, then redeploy Vercel production. Between the two steps (or with a mismatch) proxied logins fall back to the shared `direct` throttle bucket; nothing else breaks.

## Deploy Order

Always **migrate → Render → Vercel**, from a trusted local shell.

1. **Migrate** (only when the release adds migrations). In `backend/` with the venv active, set `DATABASE_URL` in this shell only and never echo it:
   ```powershell
   $env:DATABASE_URL = (neonctl connection-string --project-id sweet-dew-33937746 --database-name internship_finder --role-name internship_finder)
   alembic upgrade head
   alembic current     # expect the new head
   alembic check
   Remove-Item Env:DATABASE_URL
   ```
   Never run `alembic downgrade` against Neon. Offline `--sql` mode can't render `92a17353e5a8`; migrate online.
2. **Render:** push the reviewed commit to `main`, then **Manual Deploy → Deploy latest commit** (or `POST /v1/services/<id>/deploys`). Wait for `live`, then check `/api/health`.
3. **Vercel:** from a clean checkout of the same commit (`git worktree add --detach <dir> <sha>`), in the repository root: `npx vercel link --yes --project internship-finder --scope dude297s-projects`, then `npx vercel deploy --prod --yes`. Delete any `.env.local` the CLI creates. Verify the new deployment is aliased to `internship-finder-pi.vercel.app`.

Notes: `vercel link` appends `.vercel` and `.env*` to the checkout's `.gitignore` and writes an `.env.local` (a short-lived OIDC token), so the deployment reports `gitDirty`; delete `.env.local` and the checkout afterwards. A merge that rewrites SHAs (rebase merge) must cite the merged SHA, not the branch head, in the release record.

### Owner bootstrap (done once)

With `DATABASE_URL` set as in step 1: `python -m app.cli create-owner --username <name>`. The password goes into `getpass` only. Password rotation: `set-password` (revokes all sessions).

## Release Procedure

The order every release follows ([docs/README.md](README.md#release-closeout-contract) defines the closeout):

1. Confirm the feature PR's CI is green at the approved head and no scheduled sync is running (`gh run list --workflow sync-production.yml`).
2. Pause the scheduled sync for the window: `gh workflow disable sync-production.yml`. (Required when the migration adds rows or enum values the running code can't read; harmless otherwise.)
3. Record a read-only baseline (aggregate counts only, `READ ONLY` transaction).
4. Merge at the approved head (`gh pr merge --match-head-commit <sha>`); confirm the merged tree equals the head and post-merge CI is green.
5. [Deploy Order](#deploy-order): migrate (if any) → Render → Vercel.
6. [Production verification](#production-verification).
7. Re-enable the scheduled sync (`gh workflow enable sync-production.yml`) and dispatch it once; record its result and elapsed time. If the release bumps `RULES_VERSION` or `SCORING_VERSION`, also run `python -m app.cli reevaluate --dry-run`, then `python -m app.cli reevaluate`, from a trusted shell against production ([ADR-018](decisions/ADR-018-evaluation-staleness.md)); record the counts.
8. Owner-approved activation steps, if any ([operations.md](operations.md#source-activation-procedure)).
9. **Closeout PR (docs only):** new `docs/releases/<date>-<milestone>.md`, `docs/status.json` (then `python scripts/check_docs.py --write-status`), PROJECT_STATE.md, CHANGELOG.md. The milestone is "released — docs closeout pending" until that PR merges.

## Production Verification

Run after every deploy; record the results in the release record.

| Check | How | Expect |
|---|---|---|
| Health through Vercel | `GET https://internship-finder-pi.vercel.app/api/health` | `200 {"status":"ok"}` |
| Health on Render | `GET https://internship-finder-api-eld4.onrender.com/api/health` | `200` |
| API docs hidden | `/docs`, `/redoc`, `/openapi.json` on Render | `404` |
| Private API needs a session | `GET /api/sources`, `/api/opportunities` unauthenticated | `401` |
| Unknown API path | `GET /api/nope` | JSON `404`, not `index.html` |
| SPA deep links | `/login`, `/sources`, `/opportunities` | `200` |
| Headers | `/api/*` | `Cache-Control: no-store`, `X-Frame-Options: DENY` |
| Bundle | Current `index-*.js` | Contains the release's new UI strings; no Render hostname |
| Schema | `alembic current`, `alembic check` | At head, clean |
| Service layer (no owner password in the release shell) | The release's read-only smoke script against Neon in a `READ ONLY` transaction | All checks pass |
| Scheduled sync | One manual dispatch | Green; elapsed time well under the 20-minute limit |

The first hosted verification (2026-09-28/29: cookie attributes, CSRF, throttle buckets, cold start) is recorded in [the Milestone 3.5 release record](releases/2026-09-29-m3-5.md).

## Rollback

- **Code (Render):** Render dashboard → Deploys → **Rollback** to an earlier deploy, or deploy an earlier commit. Health check afterwards. After the `c5a1e0f3d7b2` migration, a code rollback to the Milestone 4 release is possible: the `review_state` default keeps Milestone 4's Match Profile save working on the migrated schema, so this is a normal rollback, not a schema/code coupling to avoid.
- **Frontend (Vercel):** `npx vercel rollback` (or promote an earlier production deployment in the dashboard). Hobby supports rolling back to the previous production deployment.
- **Schema:** forward only: write a new migration. Don't downgrade Neon.
- **Data:** Neon Free keeps a short restore history (point-in-time restore / branch from a past point within the free window). For anything older there's no backup yet (see [operations.md](operations.md#database-backup-implemented-not-activated-until-the-owner-configures-it)).
- **Secrets:** rotate `PROXY_SHARED_SECRET` as above; rotate the Neon role password in Neon, then update Render's `DATABASE_URL` and redeploy.
- **Milestone 5 specifically:** if Render/Vercel are rolled back to the Milestone 4 release after the `c5a1e0f3d7b2` migration, Milestone 5 data (`profile_sources`, `profile_source_artifacts`, non-manual `profile_facts`) stays in the database, unused and untouched by the Milestone 4 app, until a forward roll re-deploys Milestone 5 code.

## Cold Starts

Render Free sleeps after about 15 minutes without traffic. Observed 2026-09-28: the first proxied request arrived about 07:25 UTC, Render started the process at 07:27:46, and uvicorn was ready at 07:28:10, so the wake took **about 3 minutes**. Meanwhile Vercel answered `502` (`text/plain`, `ROUTER_EXTERNAL_TARGET_ERROR`). A second test on 2026-09-29 (Render slept at 00:53:48 UTC, request at about 01:09:33): the process started at 01:10:28 and was ready at 01:10:44. Vercel held that first request and returned `200` after **73 s**, and the existing session was still authenticated (sessions are database rows, so they survive restarts). Wake time varies from about 1 to 3 minutes. The frontend treats any non-`401` failure of the session check (network error, 5xx, non-JSON) as "server waking up", retries automatically (backoff over about a minute, each attempt also waiting on Vercel's upstream timeout), then offers **Retry**. It never treats it as a logout. No keep-alive pings, by design.

## Scheduling

Since the Milestone 6 release (2026-10-02): the GitHub Actions workflow `.github/workflows/sync-production.yml` (twice daily, 06:17 and 18:17 America/Los_Angeles, plus `workflow_dispatch`). It reads `PRODUCTION_DATABASE_URL` from the GitHub `production` **environment** secret, runs only on `main` of this repository, and never runs for pull requests or pushes ([ADR-009 amendment](decisions/ADR-009-hosted-deployment-architecture.md#amendment-2026-10-01-scheduled-source-sync-milestone-6)). Configured 2026-10-02: deployment branches restricted to `main` (custom branch policy) before the secret was added; the secret is the Neon pooled URL, piped from `neonctl connection-string --pooled` into `gh secret set PRODUCTION_DATABASE_URL --env production` (stdin, never displayed). Without the secret, every run fails fast without touching anything. No Render or Vercel cron, and no keep-alive or uptime pings.

A second workflow, `.github/workflows/backup-production.yml` ([ADR-021](decisions/ADR-021-encrypted-backups.md), unreleased, inert until activated), runs weekly (Sundays 09:43 UTC) and on dispatch with the same guards (`main` only, `production` environment, step-scoped `PRODUCTION_DATABASE_URL`, `contents: read`). It encrypts a `pg_dump` with the public age key in the repository/environment variable `BACKUP_AGE_RECIPIENT` and uploads it with 14-day retention; with the variable unset it fails fast. Owner activation and restore: [operations.md](operations.md#database-backup-implemented-not-activated-until-the-owner-configures-it).

Configuring the secret (a release step for the owner only; never in a file, a command-line argument, or chat): GitHub → Settings → Environments → **New environment** `production` → **Deployment branches: Selected branches → `main`** (required: otherwise a workflow on another branch could name the environment and read the secret; adding yourself as a required reviewer is optional) → **Add environment secret** `PRODUCTION_DATABASE_URL` with the Neon pooled `postgresql+psycopg://…?sslmode=require` URL. Or run `gh secret set PRODUCTION_DATABASE_URL --env production` and paste the value at its prompt.

## Free-Tier Behavior

- **Render Free:** sleeps when idle (cold starts above); monthly instance hours are capped. Exhaustion suspends the service, never bills.
- **Neon Free:** compute auto-suspends when idle (the first query after that is slower; `pool_pre_ping` reconnects); storage is capped (the empty schema is 8.4 MB). Exhaustion suspends compute or blocks writes, never bills.
- **Vercel Hobby:** usage limits pause or limit the project, never bill.
- Long requests: the first discovery sync (30.8 s hosted), profile re-evaluation over the whole catalog (~10 s for 1,055 opportunities hosted), and a Match Profile save that scores the whole catalog (6.4 s for 1,055 opportunities hosted, measured 2026-09-29) run inside one proxied request. None hit Vercel's external-rewrite timeout. If one ever is cut off, the backend may still finish and commit: refresh before retrying (a second sync of the same source reports "already syncing" until the first ends).

## Maintenance

Update this file whenever the production process changes. Never add secret values.
