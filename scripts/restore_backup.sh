#!/usr/bin/env bash
# Restore an encrypted backup (ADR-021) into an EMPTY database. Never targets production by itself:
# it refuses a database that already has tables, so restoring over live data is a separate,
# deliberate act (see docs/operations.md).
#
#   AGE_IDENTITY=/path/to/private.key RESTORE_DATABASE_URL=postgresql://... \
#     scripts/restore_backup.sh backup.dump.age
#
# Test hooks: PSQL, PG_RESTORE, AGE override the binaries.
set -euo pipefail

file="${1:?usage: restore_backup.sh BACKUP_FILE}"
: "${AGE_IDENTITY:?AGE_IDENTITY must point at the private age key file}"
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL must name a disposable or new database}"
url="${RESTORE_DATABASE_URL/+psycopg/}"

tables=$(${PSQL:-psql} "$url" -Atqc "select count(*) from information_schema.tables where table_schema = 'public'")
if [ "$tables" != "0" ]; then
  echo "Refusing: the target database already has $tables public tables. Restore into an empty database or a new Neon project (a Neon branch starts with production data; reset its public schema first)."
  exit 1
fi

${AGE:-age} -d -i "$AGE_IDENTITY" "$file" | ${PG_RESTORE:-pg_restore} --no-owner --no-privileges --exit-on-error --dbname="$url"

echo "Restored. Sanity check (compare with the source):"
${PSQL:-psql} "$url" -Atc "select 'alembic_version', version_num from alembic_version"
${PSQL:-psql} "$url" -Atc "select 'opportunities', count(*) from opportunities union all select 'source_records', count(*) from opportunity_source_records union all select 'sources', count(*) from ingestion_sources union all select 'profiles', count(*) from profiles"
echo "Now run 'alembic current' from backend/ with DATABASE_URL set to the restored database."
