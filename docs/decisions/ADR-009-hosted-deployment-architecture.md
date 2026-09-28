# ADR-009: Hosted Deployment Architecture

Status: Accepted

Date: 2026-09-28

## Context

Milestones 0–3 ran locally only. [ADR-004](ADR-004-technology-stack.md) selected Vercel Hobby, Render Free, and Neon Free at $0/month with no payment method. [ADR-007](ADR-007-single-user-auth-and-private-api.md) built the single-user authentication around a **same-origin** `/api` and blocked production until the hosted topology, `Secure` cookies, and login rate limiting were reviewed (ADR-007 §6, §8). Milestone 3.5 makes those concrete: which platform does what, how the browser reaches the API, how the database is migrated and bootstrapped, and what happens when a free tier runs out.

The app is single-user, private at runtime, and its source is public. Anything that would need a secret in Git, a payment card, or a second authentication system is out.

## Decision

### 1. Topology

```text
Browser
   ↓ HTTPS, one origin
Vercel Hobby — static React/Vite build + same-origin /api/* external rewrite
   ↓ HTTPS
Render Free (Oregon) — FastAPI, one instance, one uvicorn worker
   ↓ TLS (sslmode=require)
Neon Free (AWS us-west-2) — PostgreSQL 18, direct (non-pooled) endpoint
```

| Platform | Responsibility | Not used for |
|---|---|---|
| Vercel | Serve the static build; reverse-proxy `/api/*` to Render; static security headers | Backend logic, Vercel Functions, Middleware, storage, auth, Neon credentials |
| Render | Run the FastAPI application | Database (no Render Postgres), cron jobs, disk state |
| Neon | PostgreSQL | Neon Auth, Data API, serverless driver, pooled endpoint |

Explicitly **not** introduced: Supabase, Vercel Functions as the backend, Render Postgres, Neon Auth, the Neon serverless driver, any third-party authentication, Redis/Upstash, uptime/keep-alive services.

### 2. Zero-cost rule (permanent)

```text
$0/month · no card · no payment method · no paid subscription · no automatic usage billing · no automatic overage
```

- If any platform asks for payment information for a feature we need, **stop that provisioning path**. Don't enter a card. Propose an alternative (new ADR) instead.
- When a free quota runs out, the expected behavior is **sleep, pause, suspend, fail, or defer**, never a charge. All three platforms behave this way on their free plans without a payment method: Render Free sleeps and suspends; Neon Free suspends compute and caps storage; Vercel Hobby pauses or limits the project.
- No automatic paid scaling, paid add-ons, or "upgrade on overage" settings are enabled anywhere.

### 3. Same-origin browser API

- The browser calls relative `/api/...` URLs only. Vercel's `frontend/vercel.json` rewrites `/api` and `/api/*` to `https://internship-finder-api-eld4.onrender.com/api/...` **before** the SPA fallback, so unknown API paths get FastAPI's JSON `404`, not `index.html`.
- There is no `VITE_API_BASE_URL` or other backend-origin variable. The Render hostname is public information and lives in `vercel.json`.
- No CORS middleware (unchanged from ADR-007 §6): browsers can't read the API cross-origin.
- FastAPI runs with `redirect_slashes=False`, so the backend never issues a redirect whose `Location` names the Render host. Paths are exact (`/api/opportunities`, not `/api/opportunities/`).

### 4. Session cookie

The ADR-007 cookie is kept as is and is now **host-only on the Vercel hostname**: no `Domain` attribute, `HttpOnly`, `Secure` (`SESSION_COOKIE_SECURE=true`), `SameSite=Lax`, `Path=/`. Because the browser only ever talks to the Vercel origin, the cookie set by a proxied `/api/auth/login` response belongs to that origin. CSRF (the HMAC-derived `X-CSRF-Token`, kept in memory only) is unchanged.

### 5. Preserve ADR-007 authentication

The existing custom username/password + opaque server-side session + CSRF design stays. It's already reviewed and tested, keeps credentials and sessions in our own PostgreSQL, needs no signing secret, and works unchanged behind a same-origin proxy. Replacing it with Neon Auth or a third-party provider would add an external identity dependency and account setup for exactly one user, move session state out of our database, and reopen the cookie/CSRF design that ADR-007 settled. The hosted work only hardens it (§6–§7).

### 6. Login rate limiting behind the proxy

`request.client.host` on Render is Render's own proxy, and uvicorn may be configured to trust arbitrary `X-Forwarded-For`, so neither can identify a browser. The limiter now uses:

- **Per-client:** 10 failed logins per sliding 15 minutes per client key.
- **Global:** 50 failed logins per sliding 15 minutes across all clients.
- A blocked request gets `429` **before** any password work. Successful logins aren't counted and don't reset anyone's counter.

Client key:

- **Through Vercel:** Vercel's `/api` route adds `X-IF-Proxy-Secret`, whose value comes from a Vercel **Production-only, sensitive** environment variable (`PROXY_SHARED_SECRET`) via a `request.headers` transform, never from Git. When the backend's `PROXY_SHARED_SECRET` matches (constant-time compare), the key is the first `X-Forwarded-For` address. Vercel overwrites `X-Forwarded-For` with the real client address, so a browser can't forge it.
- **Anything else** (direct calls to the Render URL, a missing/wrong secret, local development): one shared key, `direct`. Headers from such callers are never trusted, so spoofing `X-Forwarded-For` gains nothing: all direct traffic shares one 10-failure bucket.

State is in memory in the single process, on purpose: one instance and one worker (§8) means one counter, and Render Free sleeps only after 15 minutes without traffic, which is the same length as the window, so a sleep-restart loses no meaningful count. A deploy restart does reset it (accepted). No database table or Redis is added.

Accepted trade-off: the global limit means an attacker with enough distinct client addresses can lock the owner out for up to 15 minutes at a time. For a single-user app, bounding total guessing and Argon2 work matters more than availability under attack.

### 7. Argon2 concurrency guard

Argon2id (`m=64 MiB, t=3, p=4`) is deliberately expensive, and Render Free has 512 MB of memory. Every hash and verify, including the dummy verification for unknown usernames, runs inside a process-wide bounded semaphore of **2** concurrent operations (~128 MiB peak for hashing). Parameters, dummy verification, and the password hash algorithm are unchanged; extra concurrent logins wait.

### 8. Render service

Free plan, Oregon, root `backend`, build `pip install .`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (one worker), health check `/api/health`, **auto-deploy off**, one instance. Environment: `DATABASE_URL` (secret), `SESSION_COOKIE_SECURE=true`, `SESSION_TTL_HOURS=24`, `PYTHON_VERSION=3.12`, `HOSTED=true`, `PROXY_SHARED_SECRET` (secret). `INGESTION_FIXTURE_FILE` is never set. `HOSTED=true` turns off `/docs`, `/redoc`, and `/openapi.json` (schema generation still works in-process) and refuses to start if `SESSION_COOKIE_SECURE` is false.

All private `/api` responses carry `Cache-Control: no-store` (set by FastAPI and again by Vercel's `/api` route). Static assets keep Vercel's normal caching.

### 9. Neon database

- Neon Free, PostgreSQL 18, `aws-us-west-2` (next to Render Oregon), database `internship_finder`.
- **Direct endpoint**, not the pooled one: there's one uvicorn process with SQLAlchemy's own pool (`pool_pre_ping=True` survives Neon compute suspends), and Alembic's DDL and transactions are simplest on a direct session.
- One `DATABASE_URL`. Neon's `postgresql://…` URL is normalized to `postgresql+psycopg://…` in application code (runtime, Alembic, and the CLI all go through it); the rest of the URL, including `sslmode` and `channel_binding`, is untouched.
- `DATABASE_URL` exists only in a trusted local shell during migration/bootstrap and in Render's secret environment. Never in Git, Vercel, the browser, PR text, docs, or logs.

### 10. Manual migrations and bootstrap

- Migrations run **by hand** from a trusted local shell (`alembic upgrade head` with `DATABASE_URL` set only in that shell), **before** deploying code that needs them. They are not in Render's build or start command.
- `alembic downgrade` is never run against Neon. Rollback is forward (a new migration) or a Neon restore (§ runbook).
- The owner is created with `python -m app.cli create-owner` from the same trusted shell; the password is typed into `getpass` and only its Argon2 hash reaches Neon.

### 11. Manual deploys, previews, and operations

- **Render:** auto-deploy off; deploys are triggered by hand after migrations. For validating an unmerged branch, the service's branch is switched to it temporarily and then back to `main` (documented in the runbook); `main` stays the review gate.
- **Vercel:** Git-triggered deployments are disabled in `vercel.json` (`git.deploymentEnabled: false`), so no branch or pull request creates a preview automatically. Production is deployed by hand from a reviewed checkout. Vercel's Standard Deployment Protection (Vercel Authentication on non-production deployments) stays on, and `PROXY_SHARED_SECRET` exists only in the Production environment, so any manually created preview can't present itself as the trusted proxy.
- **Source sync stays manual** (Sources page, API, CLI). No scheduled cloud sync, GitHub/Render/Vercel cron, keep-alive ping, or uptime monitor. Render cold starts are accepted; the frontend shows a "Server is waking up…" state with retry instead of treating an unavailable backend as logged out.

### 12. Relationship to earlier ADRs

This ADR supersedes only hosted-deployment assumptions; earlier ADRs are not rewritten.

- ADR-004's frontend-hosting constraint "don't depend on Vercel serverless/edge functions" still holds: `vercel.json` routes are platform configuration, and any reverse proxy can add the same header. ADR-004's "CORS must be configured for the Vercel origin" consequence was already replaced by ADR-007 §6 and is confirmed obsolete.
- ADR-004's GitHub Actions scheduled workflows remain the selected future scheduler, but **no schedule is enabled** in this milestone.
- ADR-007 §6's same-origin constraint is satisfied by §3–§4. ADR-007 §8's production blocker is resolved by §6–§7.

## Consequences

- One public hostname (the Vercel one) for the app. The Render URL still answers directly, but only public endpoints work without a session, and direct login attempts share one throttle bucket.
- Every API request pays a Vercel → Render hop (both US-West). Long synchronous requests (first discovery sync, profile re-evaluation across the whole catalog) are subject to Vercel's external-rewrite time limit; batching/background work is Milestone 4 debt if measurements show it's needed.
- Cold starts: the first request after ~15 idle minutes waits for Render to boot. Accepted; the UI tolerates it.
- The proxy secret must match in Vercel (Production) and Render. Rotating it is a two-place change; a mismatch degrades to the shared `direct` bucket, not to an outage.
- Migrations and deploys are manual and ordered: migrate → deploy Render → deploy Vercel.
- Offline `alembic upgrade --sql` can't render `92a17353e5a8` (it inspects the live catalog); hosted migrations always run online.

## Alternatives Considered

- **Cross-origin frontend → Render API.** Needs CORS with credentials and `SameSite=None` cookies on a third-party site, which browsers increasingly block and which weakens ADR-007's CSRF layering. Rejected; same-origin rewrite instead.
- **Migrations in the Render start command.** Every restart and cold start would run Alembic against production, a failed migration would crash-loop the service, and schema changes would happen without a human watching. Rejected; manual migration before deploy.
- **Render Postgres.** Free instances are time-limited, which doesn't fit durable personal data (as in ADR-004). Rejected.
- **Neon pooled endpoint.** PgBouncer transaction pooling adds prepared-statement and session-state caveats for no benefit with one process that already pools. Rejected for now; revisit only if the direct endpoint proves unsuitable.
- **Keep-alive pings.** Would burn Render's free instance hours and Neon compute to hide cold starts, and need another service. Rejected; the UI handles waking.
- **Automatic paid scaling / overage.** Violates the zero-cost rule. Rejected permanently.
- **Public preview deployments connected to the production backend.** Would put unreviewed frontend code on public URLs, same-origin with the real session cookie's API. Rejected: Git deployments are off, previews are protected, and the proxy secret is Production-only.
- **Trusting `X-Forwarded-For` (or uvicorn `--forwarded-allow-ips='*'`) for the limiter.** Direct callers could rotate forged addresses to get unlimited per-client buckets. Rejected in favor of the proxy-secret check.
- **Database- or Redis-backed limiter.** More moving parts than one process needs; a restart-reset is acceptable given sleep timing. Revisit if the backend ever runs more than one worker or instance.
- **Neon Auth / third-party auth.** See §5.
