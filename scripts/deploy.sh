#!/usr/bin/env bash
set -Eeuo pipefail

# Native minimal installation for Debian/Ubuntu/Astra-compatible hosts.
# Installs only the runtime stack required by the MVP: aiogram, PostgreSQL,
# Redis, provider clients and the pull-based systemd update timer.

# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
require_debian_family

install_system_packages() {
  export DEBIAN_FRONTEND=noninteractive
  log "Installing minimal operating-system dependencies"
  apt-get update
  apt-get install -y --no-install-recommends \
    ca-certificates git openssl util-linux \
    python3 python3-venv \
    postgresql postgresql-client redis-server
}

ensure_service_account() {
  if ! getent group "${APP_GROUP}" >/dev/null; then groupadd --system "${APP_GROUP}"; fi
  if ! id "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${APP_GROUP}" --create-home \
      --home-dir "/var/lib/${APP_USER}" --shell /usr/sbin/nologin "${APP_USER}"
  fi
}

create_local_database() {
  local db_name="$1" db_user="$2" db_password="$3"
  [[ "${db_name}" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || fail "Unsafe DB_NAME: ${db_name}"
  [[ "${db_user}" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || fail "Unsafe DB_USER: ${db_user}"
  [[ "${db_password}" =~ ^[a-zA-Z0-9._~-]+$ ]] || fail "DB_PASSWORD contains URL-unsafe characters"

  log "Creating or updating local PostgreSQL role"
  runuser -u postgres -- psql --set=ON_ERROR_STOP=1 \
    --set=role_name="${db_user}" --set=role_password="${db_password}" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role_name', :'role_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role_name')
\gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'role_name', :'role_password')
\gexec
SQL

  if ! runuser -u postgres -- psql -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '${db_name}'" | grep -qx '1'; then
    log "Creating local PostgreSQL database ${db_name}"
    runuser -u postgres -- createdb --owner="${db_user}" "${db_name}"
  fi
}

create_runtime_config() {
  local db_name db_user db_password token
  db_name="${DB_NAME:-crop_forecast_bot}"
  db_user="${DB_USER:-cropbot}"
  db_password="${DB_PASSWORD:-$(openssl rand -hex 24)}"
  token="${TELEGRAM_BOT_TOKEN:-}"
  if [[ -n "${TOKEN_FILE:-}" ]]; then
    [[ -r "${TOKEN_FILE}" ]] || fail "TOKEN_FILE is not readable: ${TOKEN_FILE}"
    token="$(tr -d '\r\n' < "${TOKEN_FILE}")"
  fi
  create_local_database "${db_name}" "${db_user}" "${db_password}"

  # Keep the secret file private without leaking a restrictive umask into venv
  # creation. A leaked 0027 umask made root-owned console scripts inaccessible
  # to the unprivileged cropbot runtime user on a fresh installation.
  (
    umask 0027
    cat > "${ENV_FILE}" <<EOF
APP_ENV=production
TELEGRAM_BOT_TOKEN=${token}
DATABASE_URL=postgresql+asyncpg://${db_user}:${db_password}@127.0.0.1:5432/${db_name}
REDIS_URL=redis://127.0.0.1:6379/0
COORDINATION_NAMESPACE=crop-forecast-bot
LOG_LEVEL=INFO
SCHEDULER_TIMEZONE=Europe/Moscow
HEARTBEAT_FILE=/run/crop-forecast-bot/heartbeat
OPEN_METEO_CACHE_PATH=/var/cache/crop-forecast-bot/openmeteo
RISK_HISTORY_RETENTION_DAYS=30
BLOCKING_IO_WORKERS=2
CLIMATE_REFERENCE_ENABLED=false
RISK_CHECK_ON_STARTUP=true
RISK_CHECK_STARTUP_DELAY_SECONDS=120
RAG_ENABLED=false
INSTALL_RAG_PROFILE=0
AUTO_UPDATE_ENABLED=true
AUTO_UPDATE_REQUIRE_GREEN_CI=true
GITHUB_REPOSITORY=f2re/crop_forecast_bot
GITHUB_API_URL=https://api.github.com
GITHUB_API_TOKEN=
LLM_PROVIDER=groq
GROQ_API_KEY=
TOGETHER_API_KEY=
OPENAI_API_KEY=
EOF
  )
  chown root:"${APP_GROUP}" "${ENV_FILE}"
  chmod 0640 "${ENV_FILE}"
  log "Runtime configuration created at ${ENV_FILE}"
}

repair_preflight_paths() {
  local heartbeat_dir cache_dir path
  local -a writable_paths

  heartbeat_dir="$(dirname "${HEARTBEAT_FILE:-/run/crop-forecast-bot/heartbeat}")"
  cache_dir="$(dirname "${OPEN_METEO_CACHE_PATH:-${CACHE_ROOT}/openmeteo}")"

  case "${heartbeat_dir}" in
    /run/crop-forecast-bot|/run/crop-forecast-bot/*) ;;
    *) fail "HEARTBEAT_FILE must be inside /run/crop-forecast-bot" ;;
  esac
  case "${cache_dir}" in
    "${CACHE_ROOT}"|"${CACHE_ROOT}/"*) ;;
    *) fail "OPEN_METEO_CACHE_PATH must be inside ${CACHE_ROOT}" ;;
  esac

  writable_paths=(
    "${STATE_ROOT}"
    "${STATE_ROOT}/data"
    "${STATE_ROOT}/data/literature"
    "${STATE_ROOT}/models"
    "${LOG_ROOT}"
    "${CACHE_ROOT}"
    "${cache_dir}"
    "${heartbeat_dir}"
  )

  # create_release() copies repository seed directories as root. Re-apply the
  # runtime owner after that copy and create the systemd RuntimeDirectory before
  # the deployment preflight, which intentionally runs before service start.
  install -d -m 0750 -o "${APP_USER}" -g "${APP_GROUP}" "${writable_paths[@]}"
  for path in "${writable_paths[@]}"; do
    if ! run_as_app /usr/bin/test -w "${path}"; then
      fail "Runtime path is not writable by ${APP_USER}: ${path}"
    fi
  done
}

install_system_packages
acquire_deploy_lock
ensure_service_account
prepare_runtime_directories
service_control enable --now postgresql redis-server

if [[ ! -f "${ENV_FILE}" ]]; then create_runtime_config; fi
if ! grep -Eq '^TELEGRAM_BOT_TOKEN=.+$' "${ENV_FILE}"; then
  cat >&2 <<EOF

Configuration is ready, but Telegram token is empty.
Edit ${ENV_FILE} and set TELEGRAM_BOT_TOKEN, then rerun:

  sudo editor ${ENV_FILE}
  sudo bash ${SOURCE_ROOT}/scripts/deploy.sh

Alternatively provide TOKEN_FILE=/root/cropbot-token on the next run.
EOF
  exit 2
fi

validate_runtime_env
previous_release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
create_release "${BRANCH}"
repair_preflight_paths
build_release "${NEW_RELEASE}"
backup_database
run_migrations "${NEW_RELEASE}"
preflight_release "${NEW_RELEASE}"

# Units must come from the release that will actually be activated. Rendering
# them from the bootstrap checkout can pair old unit semantics with new code.
render_systemd_units_from_release "${NEW_RELEASE}"
service_control enable "${SERVICE_NAME}"
activate_release "${NEW_RELEASE}"

if ! restart_and_verify; then
  if restore_release_after_failed_activation "${NEW_RELEASE}" "${previous_release}"; then
    fail "Service failed after deployment; previous release and its units were restored"
  fi
  fail "Service failed after deployment and no healthy previous release was available"
fi

auto_update_value="${ENABLE_AUTO_UPDATE:-${AUTO_UPDATE_ENABLED:-true}}"
validate_boolean_env "AUTO_UPDATE_ENABLED" "${auto_update_value}"
if is_true_value "${auto_update_value}"; then
  service_control enable --now "${UPDATE_TIMER_NAME}"
  log "Automatic green-main update timer enabled"
else
  service_control disable --now "${UPDATE_TIMER_NAME}" >/dev/null 2>&1 || true
  log "Automatic update timer disabled by configuration"
fi

prune_releases
log "Native MVP deployment completed: ${NEW_RELEASE_SHA}"
service_control --no-pager --full status "${SERVICE_NAME}"
