# Deployment

Hosted architecture: [ADR-009](decisions/ADR-009-hosted-deployment-architecture.md). This file is the runbook. It never contains secrets: no `DATABASE_URL`, proxy secret, password, hash, session or CSRF token.

## Status (2026-09-28)

| Part | State |
|---|---|
| Neon | **Provisioned.** Migrated to `92a17353e5a8`. Owner created (CLI, `getpass`). Catalog empty until the first hosted sync. |
| Render | **Deployed** from `feature/hosted-deployment-foundation` for hosted validation (branch switched temporarily, see [Unmerged branch validation](#unmerged-branch-validation)). Auto-deploy off. |
| Vercel | **Deployed** (production, manual CLI deploy from a clean checkout of the same branch at `af6b6f1`; nothing under `frontend/` has changed since). |
| Hosted acceptance | Verified with the owner's login on 2026-09-29 ([Production verification](#production-verification)). Render runs `36b9896` from the feature branch. |

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
| Build | `pip install .` |
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

### Owner bootstrap (done once)

With `DATABASE_URL` set as in step 1: `python -m app.cli create-owner --username <name>`. The password goes into `getpass` only. Password rotation: `set-password` (revokes all sessions).

### Unmerged branch validation

Milestone 3.5 was validated before merge by switching the Render service's branch to `feature/hosted-deployment-foundation` (auto-deploy stayed off) and deploying manually; Vercel production was deployed from a clean checkout of that branch. After the PR is merged: switch Render's branch back to `main`, deploy `main` on Render, and redeploy Vercel production from `main`. Until then, the hosted app runs the reviewed-but-unmerged branch.

## Rollback

- **Code (Render):** Render dashboard → Deploys → **Rollback** to an earlier deploy, or deploy an earlier commit. Health check afterwards.
- **Frontend (Vercel):** `npx vercel rollback` (or promote an earlier production deployment in the dashboard). Hobby supports rolling back to the previous production deployment.
- **Schema:** forward only: write a new migration. Don't downgrade Neon.
- **Data:** Neon Free keeps a short restore history (point-in-time restore / branch from a past point within the free window). For anything older there's no backup yet (see [operations.md](operations.md#database-backup-considerations-planned)).
- **Secrets:** rotate `PROXY_SHARED_SECRET` as above; rotate the Neon role password in Neon, then update Render's `DATABASE_URL` and redeploy.

## Production Verification

Run after every deploy. Results of the first hosted validation (2026-09-28) are recorded.

| Check | How | Result 2026-09-28 |
|---|---|---|
| Health through Vercel | `GET https://internship-finder-pi.vercel.app/api/health` | `200 {"status":"ok"}` |
| Database reachable from Render | A synthetic wrong login → `401` (not `500`) | `401` |
| Unknown API path | `GET /api/nope`, `GET /api` | FastAPI JSON `404`, not `index.html` |
| No slash redirect | `GET /api/health/` | `404`, no `Location` header |
| SPA deep links | `GET /login`, `/sources`, `/opportunities/123` | `200` `index.html` |
| API docs hidden | `/docs`, `/redoc`, `/openapi.json` on Render; `/api/docs` via Vercel | `404` on Render; via Vercel `/docs` etc. are the SPA shell, not API docs |
| API caching | `Cache-Control` on `/api/*` | `no-store` (also on `401`/`404`) |
| Static assets | `Cache-Control` on `/assets/*.js` | Vercel default (`public, max-age=0, must-revalidate`, edge-cached, revalidated by ETag) |
| Security headers | All responses | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` |
| Direct Render throttle | 11 wrong logins to the Render URL, each with a different forged `X-Forwarded-For` and a wrong `X-IF-Proxy-Secret` | `401` ×10, then `429`: one shared `direct` bucket |
| Proxy secret matches | While the direct bucket is full, one wrong login through Vercel | `401` (not `429`): proxied requests use their own bucket, so Render accepted the secret |
| Non-production URLs | Deployment URLs and `internship-finder-dude297s-projects.vercel.app` | `302` to Vercel SSO |
| Git pushes don't deploy | Push of the feature branch | No Vercel deployment created |
| Cold start | First request after idle | See [Cold starts](#cold-starts) |
| Session cookie (login through Vercel) | `Set-Cookie` attributes | `if_session`: `HttpOnly; Secure; SameSite=lax; Path=/; Max-Age=86400`, no `Domain` (host-only on the Vercel host) |
| CSRF | Unsafe private request without / with a wrong / with the valid `X-CSRF-Token` | `403` / `403` / `200` |
| First discovery sync (through Vercel) | Sources → Sync now | `success` in 30.8 s: 1,055 fetched, 1,055 created; 0 updated, deduplicated, unchanged, closed, invalid, errors. Finished inside the proxy window |
| Second sync | Same | `no_change` (HTTP 304) in 0.8 s |
| Profile re-evaluation (synthetic profile, 1,055 opportunities) | Save profile / change date of birth / save unchanged | 9.7 s / 9.0 s / 0.35 s (1,055 / 1,055 / 0 re-evaluated) |
| Invalid source links | `localhost`, `127.0.0.1`, `169.254.169.254`, `file://`, unknown host | `422` before any fetch |
| Credential-bearing / custom-port board links | `https://user:pw@boards.greenhouse.io/x`, `https://jobs.lever.co:8443/x` | Accepted (`201`) by `3ab655f`; only the board name was kept and nothing was fetched from them. Fixed in `65964c6` (now `422`, deployed). The two probe sources were deleted |
| Proxied throttle through Vercel | 11 wrong logins, each with different forged `X-Forwarded-For` and `X-Vercel-Forwarded-For` | Before `36b9896`: all `401` (forgeable key, see below). After: `401` ×10, then `429`; the direct bucket stays separate; existing sessions unaffected |
| Database after the first sync | Aggregate queries only | 13 MB; 1,055 opportunities, 1,055 source records, 2,110 evaluations, 2 runs |
| Session after a cold start | Idle > 15 min, then a session check through Vercel | Render restarted; `200` after 73 s; still authenticated as the owner |
| Session survives a Render redeploy | Session check after deploying `3563021` and `36b9896` | Still authenticated as the owner; catalog intact (1,055) |
| Board-link fix live | The credential and port links above, after deploying `3563021` | `422` |
| **Not run:** one Greenhouse/Lever board | | Optional; no board chosen (adding one imports all its postings, and sources can't be deleted) |

**Fixed: forgeable per-client throttle key.** On 2026-09-29, 11 wrong logins through Vercel with different forged `X-Forwarded-For` values all got `401`. A temporary diagnostic build (logging only, from a throwaway branch, removed right after) showed what Render receives: `X-Forwarded-For` is `<client>, <Vercel egress>, <Cloudflare>, <Render internal>`, and `X-Vercel-Forwarded-For` is `<client>`, but in some requests the `<client>` value in either header was the one the caller sent. No forwarded header is trustworthy, so all proxied logins now share one `proxy` bucket (`36b9896`, [ADR-009 §6 amendment](decisions/ADR-009-hosted-deployment-architecture.md#6-login-rate-limiting-behind-the-proxy)). Trade-off: 10 failed attempts by anyone through the site block new logins for 15 minutes; existing sessions keep working.

Global failed-login cap (50 per 15 minutes) is covered by unit tests only: a hosted test needs five distinct client addresses, since a blocked key stops adding failures.

## Cold Starts

Render Free sleeps after about 15 minutes without traffic. Observed 2026-09-28: the first proxied request arrived about 07:25 UTC, Render started the process at 07:27:46, and uvicorn was ready at 07:28:10, so the wake took **about 3 minutes**. Meanwhile Vercel answered `502` (`text/plain`, `ROUTER_EXTERNAL_TARGET_ERROR`). A second test on 2026-09-29 (Render slept at 00:53:48 UTC, request at about 01:09:33): the process started at 01:10:28 and was ready at 01:10:44. Vercel held that first request and returned `200` after **73 s**, and the existing session was still authenticated (sessions are database rows, so they survive restarts). Wake time varies from about 1 to 3 minutes. The frontend treats any non-`401` failure of the session check (network error, 5xx, non-JSON) as "server waking up", retries automatically (backoff over about a minute, each attempt also waiting on Vercel's upstream timeout), then offers **Retry**. It never treats it as a logout. No keep-alive pings, by design.

## Scheduling

None. Source sync stays manual (Sources page, API, or CLI with `DATABASE_URL` set as in [Deploy Order](#deploy-order)). No GitHub, Render, or Vercel cron, and no keep-alive or uptime pings. A future scheduled sync must keep `DATABASE_URL` in a repository/environment secret and never run for forked pull requests.

## Free-Tier Behavior

- **Render Free:** sleeps when idle (cold starts above); monthly instance hours are capped. Exhaustion suspends the service, never bills.
- **Neon Free:** compute auto-suspends when idle (the first query after that is slower; `pool_pre_ping` reconnects); storage is capped (the empty schema is 8.4 MB). Exhaustion suspends compute or blocks writes, never bills.
- **Vercel Hobby:** usage limits pause or limit the project, never bill.
- Long requests: the first discovery sync (30.8 s hosted) and profile re-evaluation over the whole catalog (~10 s for 1,055 opportunities hosted) run inside one proxied request. Neither hit Vercel's external-rewrite timeout on 2026-09-29. If one ever is cut off, the backend may still finish and commit: refresh before retrying (a second sync of the same source reports "already syncing" until the first ends).

## Maintenance

Update this file whenever the production process changes. Never add secret values.
