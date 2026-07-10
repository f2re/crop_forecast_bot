#!/usr/bin/env bash
set -Eeuo pipefail

# Native installation for Debian/Ubuntu/Astra-compatible hosts.
# Installs system packages, PostgreSQL/Redis, an isolated release and systemd.

# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
require_debian_family

install_system_packages() {
  export DEBIAN_FRONTEND=noninteractive
  log "Installing operating-system dependencies"
  apt-get update
  apt-get install -y --no-install-recommends \
    ca-certificates git openssl curl util-linux rsync \
    python3 python3-venv python3-dev build-essential \
    libpq-dev gdal-bin libgdal-dev \
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
RAG_ENABLED=false
INSTALL_RAG_PROFILE=0
LLM_PROVIDER=groq
GROQ_API_KEY=
TOGETHER_API_KEY=
OPENAI_API_KEY=
EOF
  chown root:"${APP_GROUP}" "${ENV_FILE}"
  chmod 0640 "${ENV_FILE}"
  log "Runtime configuration created at ${ENV_FILE}"
}

install_systemd_units() {
  local unit source
  for unit in crop-forecast-bot.service crop-forecast-bot-update.service crop-forecast-bot-update.timer; do
    source="${SOURCE_ROOT}/deploy/systemd/${unit}"
    [[ -f "${source}" ]] || fail "Missing systemd template: ${source}"
    render_template "${source}" "/etc/systemd/system/${unit}"
    chmod 0644 "/etc/systemd/system/${unit}"
  done
  systemctl daemon-reload
}

rollback_after_failed_start() {
  local previous
  previous="$(readlink -f "${PREVIOUS_LINK}" 2>/dev/null || true)"
  if [[ -n "${previous}" && -d "${previous}" ]]; then
    warn "New release failed health verification; restoring ${previous}"
    replace_symlink "${CURRENT_LINK}" "${previous}"
    systemctl restart "${SERVICE_NAME}" || true
  fi
}

install_system_packages
acquire_deploy_lock
ensure_service_account
prepare_runtime_directories
systemctl enable --now postgresql redis-server

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
install_systemd_units
create_release "${BRANCH}"
build_release "${NEW_RELEASE}"
backup_database
run_migrations "${NEW_RELEASE}"
preflight_release "${NEW_RELEASE}"
activate_release "${NEW_RELEASE}"

systemctl enable "${SERVICE_NAME}"
if ! restart_and_verify; then
  rollback_after_failed_start
  fail "Service failed after deployment; previous release was restored when available"
fi

if [[ "${ENABLE_AUTO_UPDATE:-0}" == "1" ]]; then
  systemctl enable --now "${UPDATE_TIMER_NAME}"
  log "Automatic update timer enabled"
else
  systemctl disable --now "${UPDATE_TIMER_NAME}" >/dev/null 2>&1 || true
fi

prune_releases
log "Native deployment completed: ${NEW_RELEASE_SHA}"
systemctl --no-pager --full status "${SERVICE_NAME}"
