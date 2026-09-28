# Deployment

**Deployment is not configured yet.**

Hosting and database providers are **selected** ([ADR-004](decisions/ADR-004-technology-stack.md)). The Neon database is provisioned (empty, no schema applied) and a health-only Render service is running; the frontend host and a production environment are not. The app is usable locally only.

## Blockers Before Any Hosted Deployment

The authentication design ([ADR-007](decisions/ADR-007-single-user-auth-and-private-api.md)) is **not** claimed to be Internet-production-ready. Production deployment is blocked until each item below is reviewed and resolved:

1. **Same-origin topology.** The browser must reach the API on the frontend's origin (e.g. the static host rewrites `/api/*` to the backend) or at least the same site. A frontend on one provider's random subdomain calling a backend on another provider's random subdomain is not accepted: `SameSite=Lax` cookies wouldn't be sent, and `SameSite=None` would weaken the CSRF defenses.
2. **Secure cookies.** `SESSION_COOKIE_SECURE` must be `true` (the default) and the site served only over HTTPS.
3. **Login rate limiting.** The current limiter is in memory, per process, keyed by client IP, and reset on restart. Behind a proxy it may see one IP for everyone. **Production deployment is blocked until login rate limiting is reviewed** with the real topology (trusted forwarded headers, process count, persistent or shared counters).
4. **Hosted configuration.** `DATABASE_URL` as a host secret (never in the repository or workflow YAML), migrations applied before the new code serves traffic, and the owner created with the CLI against the hosted database from a trusted machine.
5. **Owner bootstrap.** Decide how `python -m app.cli create-owner` is run against the hosted database without exposing the password (interactive `getpass` from a trusted shell).

## Cost Constraint

$0/month, and no payment method required. Before provisioning any service:

- confirm it can be created and used without a credit card or payment information
- confirm that exceeding free limits pauses, throttles, or fails rather than bills
- if either check fails, stop and propose a new ADR. Don't add a payment method.

## Hosting

| Part | Selected | Status | Notes |
|---|---|---|---|
| Frontend | Vercel Hobby | Not provisioned | Static Vite build only. No paid features, serverless functions, or Vercel storage. Portable to any static host. |
| Backend | Render Free Web Service | **Provisioned, health-only** 2026-09-27: Oregon, Python 3.12, from `main` but not redeployed since PR #6, so it runs Milestone 2 code (root `backend/`, `pip install .`, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/api/health`), auto-deploy off. `DATABASE_URL` is deliberately unset until the blockers above are resolved, so every database-backed endpoint returns 500 and no data is reachable. | Sleeps when idle; cold starts accepted. Disk isn't durable, so no persistent state on it. Must tolerate restarts. |

## Database

| Selected | Status | Notes |
|---|---|---|
| Neon PostgreSQL Free | **Provisioned** 2026-09-27 (PostgreSQL 18, `aws-us-west-2` to match Render Oregon; database and role `internship_finder`). No migrations applied yet (head is `92a17353e5a8`). | Standard Postgres only (no Neon-specific features required). Schema via Alembic. The connection string stays in Neon and host secrets only (`neonctl connection-string`), never in the repository. |

## Scheduling

GitHub Actions scheduled workflows (selected, not configured). Workflows call Python commands from the backend package. Scheduled jobs can connect to the database directly, so they don't depend on the Render service being awake.

Source sync exists as `python -m app.cli sync-sources` (Milestone 3) but runs only by hand today: the database is local, and a GitHub-hosted runner can't (and mustn't) reach it. Considerations for a future scheduled sync, once a hosted database exists:

- `DATABASE_URL` comes from a repository/environment secret, never workflow YAML, and the workflow must not run for forked pull requests.
- Keep the cadence courteous (the discovery feed updates about every 30 minutes; conditional requests make an unchanged sync nearly free). Hosted-runner minutes and Neon compute are free-tier limits: fail visibly rather than escalate ([ADR-004](decisions/ADR-004-technology-stack.md)).
- Outbound access is only to the allowlisted source hosts ([ADR-008 §10](decisions/ADR-008-opportunity-ingestion-and-deduplication.md#10-external-network-safety)). `INGESTION_FIXTURE_FILE` is test-only and must never be set in a hosted environment.
- Profile re-evaluation is synchronous (about 4 s per ~1,100 opportunities locally); a hosted instance with a request timeout may need it moved to background work first.

## Environment Variables

None are provisioned anywhere yet. Local variables are listed in [development.md](development.md#environment-variables). For production: `DATABASE_URL` (server-only secret), `SESSION_COOKIE_SECURE=true`, and optionally `SESSION_TTL_HOURS`. The frontend needs no build-time variables because it calls relative `/api` URLs; the hosting layer must route `/api` to the backend (see the blockers above). When adding more:

- list every variable in [`.env.example`](../.env.example) with placeholder values
- note here which are server-only (e.g. database URL: backend and GitHub Actions secrets only) and which may be exposed to the frontend (e.g. the public API base URL)
- never expose database credentials or secret keys to the browser. Anything in the Vite client bundle is public.

## Migration Process

Not defined yet. It must state how Alembic migrations are applied to production, in what order relative to code deploys, and who reviews them.

## Rollback Procedure

Not defined yet. It must cover rolling back code, handling migrations that can't be reversed, and restoring data.

## Production Verification

Not defined yet. It must list post-deploy checks (health, key pages/routes, a test ingestion run, logs clean).

## Maintenance

Update this file whenever the production process changes, and mark each part **Provisioned** only once it actually exists.
