# Deployment

**Deployment is not configured yet.**

No hosting provider, database provider, or production environment has been chosen. The sections below are placeholders to fill in when deployment is set up.

## Hosting

Not configured yet. TBD.

## Database

Not configured yet. TBD.

## Environment Variables

None required yet. When added:

- list every variable in [`.env.example`](../.env.example) with placeholder values
- note here which are server-only and which may be exposed to the client
- never expose service-role or secret keys to the browser

## Migration Process

Not defined yet. It must state how migrations are applied to production, in what order relative to code deploys, and who reviews them.

## Rollback Procedure

Not defined yet. It must cover rolling back code, handling migrations that can't be reversed, and restoring data.

## Production Verification

Not defined yet. It must list post-deploy checks (health, key pages/routes, a test ingestion run, logs clean).

## Maintenance

Update this file whenever the production process changes.
