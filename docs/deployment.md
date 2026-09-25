# Deployment

**Deployment is not configured yet.**

Hosting and database providers are **selected** ([ADR-004](decisions/ADR-004-technology-stack.md)) but **not provisioned**. No accounts, projects, databases, or production environment exist.

## Cost Constraint

$0/month, and no payment method required. Before provisioning any service:

- confirm it can be created and used without a credit card or payment information
- confirm that exceeding free limits pauses, throttles, or fails rather than bills
- if either check fails, stop and propose a new ADR. Don't add a payment method.

## Hosting

| Part | Selected | Status | Notes |
|---|---|---|---|
| Frontend | Vercel Hobby | Not provisioned | Static Vite build only. No paid features, serverless functions, or Vercel storage. Portable to any static host. |
| Backend | Render Free Web Service | Not provisioned | Sleeps when idle; cold starts accepted. Disk isn't durable, so no persistent state on it. Must tolerate restarts. |

## Database

| Selected | Status | Notes |
|---|---|---|
| Neon PostgreSQL Free | Not provisioned | Standard Postgres only (no Neon-specific features required). Schema via Alembic. |

## Scheduling

GitHub Actions scheduled workflows (selected, not configured). Workflows call Python commands from the backend package. Scheduled jobs can connect to the database directly, so they don't depend on the Render service being awake.

## Environment Variables

None required yet. When added:

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
