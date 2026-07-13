#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# Restore a custom-format production backup into an isolated local database and
# compare schema metadata plus exact core-table fingerprints with the source DB.
# The verification database is always dropped on exit.

# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
require_command runuser
require_command psql
require_command createdb
require_command dropdb
require_command pg_restore
validate_runtime_env

backup_file="${1:-}"
if [[ -z "${backup_file}" ]]; then
  backup_file="$(
    find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'database-*.dump' \
      -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-
  )"
fi
[[ -n "${backup_file}" && -f "${backup_file}" ]] || \
  fail "Backup file is unavailable; pass a dump path or create a backup first"

connection="${DATABASE_URL#postgresql+asyncpg://}"
authority="${connection%%/*}"
host_port="${authority##*@}"
host="${host_port%%:*}"
case "${host}" in
  127.0.0.1|localhost) ;;
  *) fail "Restore verification supports only the local native PostgreSQL instance" ;;
esac

source_database="${connection#*/}"
source_database="${source_database%%\?*}"
[[ "${source_database}" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || \
  fail "Unsafe source database name parsed from DATABASE_URL: ${source_database}"

verification_database="crop_restore_verify_$(date -u +%Y%m%d%H%M%S)_$$"
verification_database="${verification_database:0:63}"
restore_copy="$(mktemp /tmp/crop-forecast-restore-XXXXXX.dump)"

cleanup() {
  local status=$?
  trap - EXIT
  rm -f "${restore_copy}"
  runuser -u postgres -- dropdb --if-exists "${verification_database}" \
    >/dev/null 2>&1 || true
  exit "${status}"
}
trap cleanup EXIT

install -o postgres -g postgres -m 0600 "${backup_file}" "${restore_copy}"
runuser -u postgres -- createdb --template=template0 "${verification_database}"
log "Restoring ${backup_file} into isolated database ${verification_database}"
runuser -u postgres -- pg_restore \
  --exit-on-error \
  --no-owner \
  --no-privileges \
  --dbname="${verification_database}" \
  "${restore_copy}"

sql_scalar() {
  local database="$1"
  local query="$2"
  runuser -u postgres -- psql \
    --no-psqlrc \
    --set=ON_ERROR_STOP=1 \
    --tuples-only \
    --no-align \
    --dbname="${database}" \
    --command="${query}"
}

schema_query="
SELECT md5(COALESCE(string_agg(
  table_name || '|' || ordinal_position || '|' || column_name || '|' ||
  data_type || '|' || is_nullable || '|' || COALESCE(column_default, ''),
  E'\\n' ORDER BY table_name, ordinal_position
), ''))
FROM information_schema.columns
WHERE table_schema = 'public';"

source_schema="$(sql_scalar "${source_database}" "${schema_query}")"
restored_schema="$(sql_scalar "${verification_database}" "${schema_query}")"
[[ -n "${source_schema}" && "${source_schema}" == "${restored_schema}" ]] || \
  fail "Restored schema fingerprint differs from the source database"

revision_query="
SELECT COALESCE(string_agg(version_num, ',' ORDER BY version_num), '')
FROM alembic_version;"
source_revision="$(sql_scalar "${source_database}" "${revision_query}")"
restored_revision="$(sql_scalar "${verification_database}" "${revision_query}")"
[[ -n "${source_revision}" && "${source_revision}" == "${restored_revision}" ]] || \
  fail "Alembic revision differs after restore: ${source_revision} != ${restored_revision}"

for table in users fields crop_seasons; do
  exists_query="SELECT to_regclass('public.${table}') IS NOT NULL;"
  [[ "$(sql_scalar "${source_database}" "${exists_query}")" == "t" ]] || \
    fail "Source database is missing required table: ${table}"
  [[ "$(sql_scalar "${verification_database}" "${exists_query}")" == "t" ]] || \
    fail "Restored database is missing required table: ${table}"

  fingerprint_query="
SELECT count(*)::text || ':' || md5(COALESCE(string_agg(
  row_to_json(t)::text,
  E'\\n' ORDER BY row_to_json(t)::text
), ''))
FROM public.${table} AS t;"
  source_fingerprint="$(sql_scalar "${source_database}" "${fingerprint_query}")"
  restored_fingerprint="$(sql_scalar "${verification_database}" "${fingerprint_query}")"
  [[ "${source_fingerprint}" == "${restored_fingerprint}" ]] || \
    fail "Data fingerprint differs after restore for table ${table}"
  log "Verified ${table}: ${source_fingerprint%%:*} rows"
done

log "Backup restore verification passed at Alembic revision ${source_revision}"
