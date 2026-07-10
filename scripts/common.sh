#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

APP_NAME="${APP_NAME:-crop-forecast-bot}"
APP_USER="${APP_USER:-cropbot}"
APP_GROUP="${APP_GROUP:-${APP_USER}}"
APP_ROOT="${APP_ROOT:-/opt/crop-forecast-bot}"
RELEASES_DIR="${RELEASES_DIR:-${APP_ROOT}/releases}"
CURRENT_LINK="${CURRENT_LINK:-${APP_ROOT}/current}"
PREVIOUS_LINK="${PREVIOUS_LINK:-${APP_ROOT}/previous}"
STATE_ROOT="${STATE_ROOT:-/var/lib/crop-forecast-bot}"
CACHE_ROOT="${CACHE_ROOT:-/var/cache/crop-forecast-bot}"
LOG_ROOT="${LOG_ROOT:-/var/log/crop-forecast-bot}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/crop-forecast-bot}"
ENV_FILE="${ENV_FILE:-/etc/crop-forecast-bot.env}"
REPO_URL="${REPO_URL:-https://github.com/f2re/crop_forecast_bot.git}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-crop-forecast-bot.service}"
UPDATE_TIMER_NAME="${UPDATE_TIMER_NAME:-crop-forecast-bot-update.timer}"
LOCK_FILE="${LOCK_FILE:-/run/lock/crop-forecast-bot-deploy.lock}"
KEEP_RELEASES="${KEEP_RELEASES:-4}"
KEEP_BACKUPS="${KEEP_BACKUPS:-7}"

NEW_RELEASE=""
NEW_RELEASE_SHA=""

log() { printf '[%s] %s\n' "${APP_NAME}" "$*" >&2; }
warn() { printf '[%s] WARNING: %s\n' "${APP_NAME}" "$*" >&2; }
fail() { printf '[%s] ERROR: %s\n' "${APP_NAME}" "$*" >&2; exit 1; }
require_root() { [[ "${EUID}" -eq 0 ]] || fail "Run this command as root"; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"; }

require_debian_family() {
  [[ -r /etc/os-release ]] || fail "/etc/os-release is unavailable"
  # shellcheck disable=SC1091
  source /etc/os-release
  case " ${ID:-} ${ID_LIKE:-} " in
    *debian*|*ubuntu*) ;;
    *) fail "Automatic installation currently supports Debian/Ubuntu/Astra-compatible hosts" ;;
  esac
}

acquire_deploy_lock() {
  require_command flock
  install -d -m 0755 "$(dirname "${LOCK_FILE}")"
  exec 9>"${LOCK_FILE}"
  flock -n 9 || fail "Another deployment or update is already running"
}

load_runtime_env() {
  [[ -r "${ENV_FILE}" ]] || fail "Runtime configuration is missing: ${ENV_FILE}"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
}

validate_runtime_env() {
  load_runtime_env
  [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] || fail "TELEGRAM_BOT_TOKEN is empty in ${ENV_FILE}"
  [[ "${TELEGRAM_BOT_TOKEN}" != *YOUR_* ]] || fail "Replace the placeholder Telegram token"
  [[ -n "${DATABASE_URL:-}" ]] || fail "DATABASE_URL is empty in ${ENV_FILE}"
  [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]] || \
    fail "Native production deployment requires postgresql+asyncpg:// DATABASE_URL"
  [[ -n "${REDIS_URL:-}" ]] || fail "REDIS_URL is empty in ${ENV_FILE}"
  case "${RAG_ENABLED:-false}" in
    true|false|1|0|yes|no|on|off) ;;
    *) fail "RAG_ENABLED must be a boolean value" ;;
  esac
  if [[ "${RAG_ENABLED:-false}" =~ ^(true|1|yes|on)$ ]] && \
     [[ "${INSTALL_RAG_PROFILE:-0}" != "1" ]]; then
    fail "RAG_ENABLED requires INSTALL_RAG_PROFILE=1"
  fi
}

run_as_app() {
  runuser -u "${APP_USER}" --preserve-environment -- \
    env HOME="${STATE_ROOT}" XDG_CACHE_HOME="${CACHE_ROOT}" "$@"
}

run_as_app_in_release() {
  local release="$1"
  shift
  (cd "${release}" && run_as_app "$@")
}

prepare_runtime_directories() {
  install -d -m 0755 "${APP_ROOT}" "${RELEASES_DIR}"
  install -d -m 0750 -o "${APP_USER}" -g "${APP_GROUP}" \
    "${STATE_ROOT}" "${STATE_ROOT}/data" "${STATE_ROOT}/data/literature" \
    "${STATE_ROOT}/models" "${CACHE_ROOT}" "${CACHE_ROOT}/pip" \
    "${CACHE_ROOT}/huggingface" "${LOG_ROOT}"
  install -d -m 0700 "${BACKUP_ROOT}"
}

link_persistent_directory() {
  local release="$1" name="$2" target="$3" source_path="${release}/$2"
  install -d -m 0750 -o "${APP_USER}" -g "${APP_GROUP}" "${target}"
  if [[ -d "${source_path}" && ! -L "${source_path}" ]]; then
    cp -a -n "${source_path}/." "${target}/" 2>/dev/null || true
  fi
  rm -rf "${source_path}"
  ln -s "${target}" "${source_path}"
}

prepare_release_layout() {
  local release="$1"
  link_persistent_directory "${release}" data "${STATE_ROOT}/data"
  link_persistent_directory "${release}" models "${STATE_ROOT}/models"
  link_persistent_directory "${release}" logs "${LOG_ROOT}"
}

create_release() {
  local branch="${1:-${BRANCH}}" timestamp staging final
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  staging="${RELEASES_DIR}/.staging-${timestamp}-$$"
  rm -rf "${staging}"
  log "Cloning ${REPO_URL} branch ${branch}"
  git clone --depth 1 --single-branch --branch "${branch}" "${REPO_URL}" "${staging}"
  NEW_RELEASE_SHA="$(git -C "${staging}" rev-parse HEAD)"
  final="${RELEASES_DIR}/${timestamp}-${NEW_RELEASE_SHA:0:12}"
  [[ ! -e "${final}" ]] || fail "Release already exists: ${final}"
  mv "${staging}" "${final}"
  NEW_RELEASE="${final}"
  prepare_release_layout "${NEW_RELEASE}"
  log "Created release ${NEW_RELEASE_SHA:0:12} at ${NEW_RELEASE}"
}

build_release() {
  local release="$1" requirements_file="${release}/requirements.txt"
  if [[ "${INSTALL_RAG_PROFILE:-0}" == "1" ]]; then
    requirements_file="${release}/requirements-rag.txt"
    log "Optional RAG dependency profile is enabled"
  fi
  log "Creating isolated Python environment"
  python3 -m venv "${release}/.venv"
  PIP_CACHE_DIR="${CACHE_ROOT}/pip" "${release}/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
  PIP_CACHE_DIR="${CACHE_ROOT}/pip" "${release}/.venv/bin/python" -m pip install -r "${requirements_file}"
  "${release}/.venv/bin/python" -m pip check
  "${release}/.venv/bin/python" -m compileall -q "${release}/alembic" "${release}/config" "${release}/src"
}

preflight_release() {
  local release="$1"
  validate_runtime_env
  log "Running runtime preflight for ${release}"
  run_as_app_in_release "${release}" "${release}/.venv/bin/python" -m src.ops.doctor --runtime
}

run_migrations() {
  local release="$1"
  [[ -f "${release}/alembic.ini" ]] || fail "Release does not contain alembic.ini"
  [[ -x "${release}/.venv/bin/alembic" ]] || fail "Release virtualenv does not contain Alembic"
  log "Applying Alembic migrations"
  run_as_app_in_release "${release}" "${release}/.venv/bin/alembic" upgrade head
}

replace_symlink() {
  local link_path="$1" target="$2" temporary="${1}.new.$$"
  rm -f "${temporary}"
  ln -s "${target}" "${temporary}"
  mv -Tf "${temporary}" "${link_path}"
}

activate_release() {
  local release="$1" old_release=""
  old_release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
  if [[ -n "${old_release}" && -d "${old_release}" ]]; then
    replace_symlink "${PREVIOUS_LINK}" "${old_release}"
  fi
  replace_symlink "${CURRENT_LINK}" "${release}"
}

heartbeat_is_fresh() {
  local heartbeat_file="${HEARTBEAT_FILE:-/run/crop-forecast-bot/heartbeat}"
  [[ -x "${CURRENT_LINK}/.venv/bin/python" ]] || return 1
  (cd "${CURRENT_LINK}" && "${CURRENT_LINK}/.venv/bin/python" -m src.ops.heartbeat "${heartbeat_file}" --max-age 120)
}

restart_and_verify() {
  local attempt
  load_runtime_env
  rm -f "${HEARTBEAT_FILE:-/run/crop-forecast-bot/heartbeat}" || true
  systemctl restart "${SERVICE_NAME}"
  for ((attempt = 1; attempt <= 45; attempt++)); do
    if systemctl is-active --quiet "${SERVICE_NAME}" && heartbeat_is_fresh; then
      log "Service is active and heartbeat is current"
      return 0
    fi
    systemctl is-failed --quiet "${SERVICE_NAME}" && break
    sleep 2
  done
  journalctl -u "${SERVICE_NAME}" -n 100 --no-pager >&2 || true
  return 1
}

backup_database() {
  local dsn backup_file temporary
  if [[ "${SKIP_DATABASE_BACKUP:-0}" == "1" ]]; then warn "Database backup was explicitly skipped"; return 0; fi
  validate_runtime_env
  require_command pg_dump
  dsn="${DATABASE_URL/postgresql+asyncpg:\/\//postgresql:\/\/}"
  backup_file="${BACKUP_ROOT}/database-$(date -u +%Y%m%dT%H%M%SZ).dump"
  temporary="${backup_file}.tmp"
  log "Creating PostgreSQL backup"
  pg_dump --format=custom --file="${temporary}" "${dsn}"
  chmod 0600 "${temporary}"
  mv "${temporary}" "${backup_file}"
  log "Database backup stored at ${backup_file}"
  prune_backups
}

prune_backups() {
  local index
  local -a backups=()
  mapfile -t backups < <(find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'database-*.dump' -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-)
  for ((index = KEEP_BACKUPS; index < ${#backups[@]}; index++)); do rm -f "${backups[index]}"; done
}

prune_releases() {
  local current previous index release
  local -a releases=()
  current="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
  previous="$(readlink -f "${PREVIOUS_LINK}" 2>/dev/null || true)"
  mapfile -t releases < <(find "${RELEASES_DIR}" -mindepth 1 -maxdepth 1 -type d ! -name '.staging-*' -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-)
  for ((index = KEEP_RELEASES; index < ${#releases[@]}; index++)); do
    release="${releases[index]}"
    [[ "${release}" == "${current}" || "${release}" == "${previous}" ]] && continue
    log "Removing old release ${release}"
    rm -rf "${release}"
  done
}

render_template() {
  local source="$1" target="$2"
  sed -e "s|@APP_USER@|${APP_USER}|g" -e "s|@APP_GROUP@|${APP_GROUP}|g" \
    -e "s|@APP_ROOT@|${APP_ROOT}|g" -e "s|@CURRENT_LINK@|${CURRENT_LINK}|g" \
    -e "s|@ENV_FILE@|${ENV_FILE}|g" -e "s|@BRANCH@|${BRANCH}|g" \
    "${source}" > "${target}"
}
