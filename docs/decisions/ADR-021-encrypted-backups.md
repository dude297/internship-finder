# ADR-021: Encrypted Database Backups

Status: Proposed (on the feature branch `feature/m12-encrypted-backup`; subject to owner review)

Date: 2026-10-06

## Context

The known debt was "no database backups beyond Neon Free's short restore window". The constraints:

- **$0, no payment method** ([ADR-004](ADR-004-technology-stack.md)): no paid storage, no card-backed account.
- **The repository is public** ([ENGINEERING_GUIDELINES.md §16](../../ENGINEERING_GUIDELINES.md#16-public-repository-security-and-privacy)). Workflow logs are public, and artifacts of a public repository are downloadable by any signed-in GitHub user. The database holds the owner's private profile, so a backup must be unreadable to everyone but the owner.
- The scheduled sync already established the pattern for a production-database job ([ADR-009 amendment of 2026-10-01](ADR-009-hosted-deployment-architecture.md#amendment-2026-10-01-scheduled-source-sync-milestone-6)): schedule and dispatch only, `main`-only, the `production` environment, a step-scoped secret.

## Decision

A weekly GitHub Actions workflow, `.github/workflows/backup-production.yml` (plus `workflow_dispatch`), runs `scripts/backup_db.sh`: `pg_dump --format=custom | age -r <public key> > file`, then uploads the file as an artifact with `retention-days: 14`.

1. **Encrypt before the data leaves the process.** `pg_dump` is piped straight into `age`; no plaintext file exists and nothing plaintext reaches a log. A failed dump fails the job (`pipefail`) and the partial file is deleted. The encrypted file must be at least 8 KiB and start with the age header, or it is discarded.
2. **Asymmetric, so CI holds no decryption secret.** Only the age *public* key (the repository/environment variable `BACKUP_AGE_RECIPIENT`) is in GitHub. The owner generates the key pair offline (`age-keygen -pq`, hybrid post-quantum, recommended because ciphertext stays downloadable) and keeps the private key offline; the recipient is validated as `age1<58 chars>` or `age1pq1...`. Anyone who downloads the artifact, or who compromises the workflow, can't read it.
3. **Nothing runs until the owner configures it.** An empty variable (or secret) fails the first step with a fixed message before any database access.
4. **Reuse the `production` environment and `PRODUCTION_DATABASE_URL`.** `PGSSLMODE` defaults to `require`; core dumps are disabled; `pg_dump`/`psql` stderr goes to a temp file that is deleted (the public log shows only a fixed message and exit codes); in Actions the URL, host, role and password are `::add-mask::`ed first; a pre-dump `select count(*) from opportunities` refuses an empty or unreachable database. The secret is step-scoped; the script strips the SQLAlchemy `+psycopg` suffix and swaps Neon's `-pooler` host for the direct host (pgbouncer's transaction mode isn't safe for `pg_dump`) in-shell, without echoing. No shell tracing.
5. **Supply chain.** Actions pinned to commit SHAs; `age` v1.3.2 downloaded from its GitHub release and verified against a pinned SHA-256 (a trust-on-first-use pin: it detects a changed download, not an upstream compromised before pinning); the PostgreSQL 18 client comes from the PGDG apt repository, whose signing key's fingerprint is checked against the published one, on a pinned `ubuntu-24.04` image. `pg_dump` must report major 18 to match the server.
6. **Retention limits storage, not exposure.** Artifacts expire after 14 days (about two weekly backups), but anyone signed in to GitHub can download and keep the ciphertext meanwhile. Confidentiality therefore rests entirely on the private key, not on expiry. The artifact name carries only the date.
7. **Restore is a separate, deliberate tool.** `scripts/restore_backup.sh` decrypts with the offline key into an *empty* database (a disposable local database, a new Neon project, or a Neon branch reset with `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`, because a Neon branch starts with a copy of production data) and refuses a non-empty target, so it can't overwrite production by accident. A restore that fails under `--exit-on-error` leaves a partial database; use a fresh target for the retry. Restoring over production is a manual, documented, owner-only procedure.
8. **A text-level test** (`scripts/tests/test_backup_workflow.py`, run by CI's unittest discovery) keeps the workflow's security invariants from regressing.

## Alternatives considered

- **Neon branches / point-in-time restore only.** Free, but the history window on the Free plan is short, so it doesn't cover a mistake found late, and it lives with the same provider and account. Kept as a complement, not a backup.
- **Symmetric encryption (GPG or `age -p`) with a passphrase secret.** Rejected: the decryption secret would live in GitHub next to the data, so a workflow compromise would also decrypt every stored backup.
- **External storage (S3, Backblaze, Drive).** Rejected: new accounts, credentials in CI, and usually a card or a paid tier.
- **Committing encrypted dumps to the repository.** Rejected: the public history is permanent, so retention couldn't be bounded.
- **Unencrypted artifact in a private repository.** Not available: the repository is public.

## Consequences

- Backups exist only after the owner sets `BACKUP_AGE_RECIPIENT` and dispatches once; the implementation is inert before that.
- **Key compromise discloses every past backup** still held by anyone who downloaded the ciphertext, and rotating the key doesn't recall them. Treat the private key like the database credential.
- **Losing the private key makes every backup unreadable.** The owner stores it in a password manager and one offline copy.
- An artifact is a snapshot of the whole database, including auth and profile tables. It is as sensitive as the database; encryption is mandatory, not optional.
- GitHub disables scheduled workflows in a public repository after 60 days without repository activity; nothing alerts. The backup then stops silently (same caveat as the sync).
- Recovery depth is about two weekly points; a restore test into a new Neon branch or a local database is part of activation.
- A compromised workflow can still read the production database (it holds the same secret as the sync); this ADR doesn't widen that. A least-privilege read-only role for the backup is the next hardening step.
