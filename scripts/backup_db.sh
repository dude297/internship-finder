#!/usr/bin/env bash
# Encrypted database backup (ADR-021). Streams pg_dump straight into `age`, so plaintext never
# touches disk or a log. Only the PUBLIC recipient key is needed; the private key stays offline.
#
#   DATABASE_URL=... BACKUP_AGE_RECIPIENT=age1... scripts/backup_db.sh OUTPUT.dump.age
#
# Test hooks: PG_DUMP and AGE override the binaries (e.g. PG_DUMP="docker compose exec -T postgres pg_dump").
# No shell tracing: the URL carries the database password.
set -euo pipefail

out="${1:?usage: backup_db.sh OUTPUT_FILE}"
min_bytes="${BACKUP_MIN_BYTES:-8192}"

if [ -z "${BACKUP_AGE_RECIPIENT:-}" ]; then
  echo "::error::BACKUP_AGE_RECIPIENT is empty; set it as a repository or environment variable (public age key)."
  exit 1
fi
case "$BACKUP_AGE_RECIPIENT" in
  age1*) ;;
  *) echo "::error::BACKUP_AGE_RECIPIENT must be an age public key (age1...)."; exit 1 ;;
esac
if [ -z "${DATABASE_URL:-}" ]; then
  echo "::error::DATABASE_URL is empty; configure PRODUCTION_DATABASE_URL on the production environment."
  exit 1
fi

# pg_dump needs a libpq URL: drop the SQLAlchemy driver suffix, and use Neon's direct endpoint
# (the pooler runs pgbouncer in transaction mode, which pg_dump can't rely on).
url="${DATABASE_URL/+psycopg/}"
url="${url/-pooler./.}"

umask 077
# ponytail: if pg_dump fails, pipefail fails this line and the truncated file is deleted below.
if ! ${PG_DUMP:-pg_dump} --format=custom --no-owner --no-privileges --dbname="$url" \
  | ${AGE:-age} -r "$BACKUP_AGE_RECIPIENT" > "$out"; then
  rm -f "$out"
  echo "::error::Backup failed (pg_dump or age exited non-zero); no artifact written."
  exit 1
fi

size=$(wc -c < "$out")
if [ "$size" -lt "$min_bytes" ]; then
  rm -f "$out"
  echo "::error::Encrypted backup is only $size bytes (minimum $min_bytes); refusing to keep it."
  exit 1
fi
if [ "$(head -c 21 "$out")" != "age-encryption.org/v1" ]; then
  rm -f "$out"
  echo "::error::Output is not an age file; refusing to keep it."
  exit 1
fi
echo "Encrypted backup written: $size bytes."
