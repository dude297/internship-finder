#!/usr/bin/env bash
# Encrypted database backup (ADR-021). Streams pg_dump straight into `age`, so plaintext never
# touches disk or a log. Only the PUBLIC recipient key is needed; the private key stays offline.
#
#   DATABASE_URL=... BACKUP_AGE_RECIPIENT=age1... scripts/backup_db.sh OUTPUT.dump.age
#
# Test hooks: PG_DUMP, PSQL and AGE override the binaries (e.g. PG_DUMP="docker exec -i c pg_dump").
# No shell tracing: the URL carries the database password. Tool stderr (libpq can print the host
# or role) goes to a temp file that is deleted, never to the public Actions log.
set -euo pipefail
ulimit -c 0 2>/dev/null || true # no core dump of a process holding the URL
export PGSSLMODE="${PGSSLMODE:-require}"

out="${1:?usage: backup_db.sh OUTPUT_FILE}"
min_bytes="${BACKUP_MIN_BYTES:-8192}"

if [ -z "${BACKUP_AGE_RECIPIENT:-}" ]; then
  echo "::error::BACKUP_AGE_RECIPIENT is empty; set it as a repository or environment variable (public age key)."
  exit 1
fi
if ! [[ "$BACKUP_AGE_RECIPIENT" =~ ^age1[a-z0-9]{58}$ || "$BACKUP_AGE_RECIPIENT" =~ ^age1pq1[a-z0-9]+$ ]]; then
  echo "::error::BACKUP_AGE_RECIPIENT is not a valid age public key (age1... or age1pq1...)."
  exit 1
fi
if [ -z "${DATABASE_URL:-}" ]; then
  echo "::error::DATABASE_URL is empty; configure PRODUCTION_DATABASE_URL on the production environment."
  exit 1
fi

# pg_dump needs a libpq URL: drop the SQLAlchemy driver suffix, and use Neon's direct endpoint
# (the pooler runs pgbouncer in transaction mode, which pg_dump can't rely on).
url="${DATABASE_URL/+psycopg/}"
url="${url/-pooler./.}"

if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
  # Mask the URL and its parts before anything can print them (parsed in-shell, never echoed).
  rest="${url#*://}"
  userinfo="${rest%%@*}"
  hostpart="${rest#*@}"
  for v in "$DATABASE_URL" "$url" "${userinfo%%:*}" "${userinfo#*:}" "${hostpart%%[/:?]*}"; do
    [ -n "$v" ] && echo "::add-mask::$v"
  done
fi

# Keep the password out of argv (visible to other processes on the runner): libpq reads
# PGPASSWORD when the URL carries none. Percent-decoded, since the URL form is encoded.
rest="${url#*://}"
userinfo="${rest%%@*}"
if [[ "$rest" == *@* && "$userinfo" == *:* ]]; then
  pw="${userinfo#*:}"
  hex='\x' # a literal: a backslash typed inside "${...}" would be dropped
  PGPASSWORD="$(printf '%b' "${pw//%/$hex}")"
  export PGPASSWORD
  url="${url%%://*}://${userinfo%%:*}@${rest#*@}"
fi

errfile="${RUNNER_TEMP:-/tmp}/backup-tools.$$.err"
trap 'rm -f "$errfile"' EXIT
: > "$errfile"
umask 077

# Sanity: refuse to back up an empty or unreadable database.
rows=$(${PSQL:-psql} "$url" -Atc "select count(*) from opportunities" 2>>"$errfile" || true)
if ! [[ "$rows" =~ ^[0-9]+$ ]] || [ "$rows" -eq 0 ]; then
  echo "::error::Pre-dump check failed: the database is unreachable or has no opportunities. Tool output withheld."
  exit 1
fi

set +e
${PG_DUMP:-pg_dump} --format=custom --no-owner --no-privileges --dbname="$url" 2>>"$errfile" \
  | ${AGE:-age} -r "$BACKUP_AGE_RECIPIENT" 2>>"$errfile" > "$out"
codes=("${PIPESTATUS[@]}")
set -e
# ponytail: pipefail-equivalent check by hand so a failed pg_dump never leaves a truncated file.
if [ "${codes[0]}" -ne 0 ] || [ "${codes[1]}" -ne 0 ]; then
  rm -f "$out"
  echo "::error::Backup failed (pg_dump exit ${codes[0]}, age exit ${codes[1]}); no artifact written. Tool output withheld."
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
