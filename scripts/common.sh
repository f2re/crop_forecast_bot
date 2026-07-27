#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC2034
SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

APP_NAME="${APP_NAME:-crop-forecast-bot}"
APP_USER="${APP_USER:-cropbot}"
APP_GROUP="${APP_GROUP:-${APP_USER}}"
APP_ROOT="${APP_ROOT:-/opt/crop-forecast-bot}"
RELEASES_DIR="${RELEASES_DIR:-${APP_ROOT}/releases}"
CURRENT_LINK="${CURRENT_LINK:-${APP_ROOT}/current}"
PREVIOUS_LINK="${PREVIOUS_LINK:-${APP_ROOT}/previous}"
STATE_ROOT="${STATE_ROOT:-/var/lib/crop-forecast-bot}"
VENV_ROOT="${VENV_ROOT:-${STATE_ROOT}/venvs}"
CACHE_ROOT="${CACHE_ROOT:-/var/cache/crop-forecast-bot}"
LOG_ROOT="${LOG_ROOT:-/var/log/crop-forecast-bot}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/crop-forecast-bot}"
ENV_FILE="${ENV_FILE:-/etc/crop-forecast-bot.env}"
REPO_URL="${REPO_URL:-https://github.com/f2re/crop_forecast_bot.git}"
GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-f2re/crop_forecast_bot}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-crop-forecast-bot.service}"
UPDATE_TIMER_NAME="${UPDATE_TIMER_NAME:-crop-forecast-bot-update.timer}"
LOCK_FILE="${LOCK_FILE:-/run/lock/crop-forecast-bot-deploy.lock}"
KEEP_RELEASES="${KEEP_RELEASES:-2}"
KEEP_BACKUPS="${KEEP_BACKUPS:-3}"
SYSTEMD_UNIT_DIR="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"
JOURNALCTL_BIN="${JOURNALCTL_BIN:-journalctl}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HEALTHCHECK_ATTEMPTS="${HEALTHCHECK_ATTEMPTS:-45}"
HEALTHCHECK_INTERVAL_SECONDS="${HEALTHCHECK_INTERVAL_SECONDS:-2}"

readonly -a SYSTEMD_UNITS=(
  crop-forecast-bot.service
  crop-forecast-bot-update.service
  crop-forecast-bot-update.timer
)

NEW_RELEASE=""
NEW_RELEASE_SHA=""

log() {
  printf '[%s] %s\n' "${APP_NAME}" "$*" >&2
}

warn() {
  printf '[%s] WARNING: %s\n' "${APP_NAME}" "$*" >&2
}

fail() {
  printf '[%s] ERROR: %s\n' "${APP_NAME}" "$*" >&2
  exit 1
}

require_root() {
  [[ "${EUID}" -eq 0 ]] || fail "Run this command as root"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

require_debian_family() {
  [[ -r /etc/os-release ]] || fail "/etc/os-release is unavailable"
  # shellcheck disable=SC1091
  source /etc/os-release
  case " ${ID:-} ${ID_LIKE:-} " in
    *debian*|*ubuntu*) ;;
    *) fail "Automatic installation currently supports Debian/Ubuntu/Astra-compatible hosts" ;;
  esac
}

service_control() {
  "${SYSTEMCTL_BIN}" "$@"
}

service_journal() {
  "${JOURNALCTL_BIN}" "$@"
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

validate_boolean_env() {
  local name="$1"
  local value="$2"
  case "${value}" in
    true|false|1|0|yes|no|on|off) ;;
    *) fail "${name} must be a boolean value" ;;
  esac
}

is_true_value() {
  case "${1:-false}" in
    true|1|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

validate_runtime_env() {
  load_runtime_env
  [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] || fail "TELEGRAM_BOT_TOKEN is empty in ${ENV_FILE}"
  [[ "${TELEGRAM_BOT_TOKEN}" != *YOUR_* ]] || fail "Replace the placeholder Telegram token"
  [[ -n "${DATABASE_URL:-}" ]] || fail "DATABASE_URL is empty in ${ENV_FILE}"
  [[ "${DATABASE_URL}" == postgresql+asyncpg://* ]] || \
    fail "Native production deployment requires postgresql+asyncpg:// DATABASE_URL"
  [[ -n "${REDIS_URL:-}" ]] || fail "REDIS_URL is empty in ${ENV_FILE}"

  validate_boolean_env "RAG_ENABLED" "${RAG_ENABLED:-false}"
  validate_boolean_env \
    "CLIMATE_REFERENCE_ENABLED" "${CLIMATE_REFERENCE_ENABLED:-false}"
  validate_boolean_env "AUTO_UPDATE_ENABLED" "${AUTO_UPDATE_ENABLED:-true}"
  validate_boolean_env \
    "AUTO_UPDATE_REQUIRE_GREEN_CI" "${AUTO_UPDATE_REQUIRE_GREEN_CI:-true}"
  validate_boolean_env "RISK_CHECK_ON_STARTUP" "${RISK_CHECK_ON_STARTUP:-true}"

  if is_true_value "${RAG_ENABLED:-false}" && \
     [[ "${INSTALL_RAG_PROFILE:-0}" != "1" ]]; then
    fail "RAG_ENABLED requires INSTALL_RAG_PROFILE=1"
  fi
  if is_true_value "${AUTO_UPDATE_REQUIRE_GREEN_CI:-true}"; then
    [[ "${GITHUB_REPOSITORY:-}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || \
      fail "GITHUB_REPOSITORY must use owner/name format"
  fi
}

run_as_app() {
  runuser -u "${APP_USER}" --preserve-environment -- \
    env HOME="${STATE_ROOT}" XDG_CACHE_HOME="${CACHE_ROOT}" "$@"
}

run_as_app_in_release() {
  local release="$1"
  shift
  (
    cd "${release}"
    run_as_app "$@"
  )
}

prepare_runtime_directories() {
  install -d -m 0755 "${APP_ROOT}" "${RELEASES_DIR}" "${VENV_ROOT}"
  install -d -m 0750 -o "${APP_USER}" -g "${APP_GROUP}" \
    "${STATE_ROOT}" "${STATE_ROOT}/data" "${STATE_ROOT}/data/literature" \
    "${STATE_ROOT}/models" "${CACHE_ROOT}" "${CACHE_ROOT}/pip" \
    "${CACHE_ROOT}/huggingface" "${LOG_ROOT}"
  install -d -m 0700 "${BACKUP_ROOT}"
}

link_persistent_directory() {
  local release="$1"
  local name="$2"
  local target="$3"
  local source_path="${release}/${name}"

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

remote_branch_sha() {
  local branch="${1:-${BRANCH}}"
  local output sha
  output="$(git ls-remote --exit-code --heads "${REPO_URL}" "refs/heads/${branch}")" || \
    return 1
  sha="$(printf '%s\n' "${output}" | awk 'NR == 1 {print $1}')"
  [[ "${sha}" =~ ^[0-9a-fA-F]{40}$ ]] || return 1
  printf '%s\n' "${sha,,}"
}

create_release() {
  local branch="${1:-${BRANCH}}"
  local timestamp staging final
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
  local release="$1"
  local requirements_file="${release}/requirements.txt"
  local python_version requirements_hash shared_venv staging_venv
  local -a fingerprint_files=("${release}/requirements.txt")

  if [[ "${INSTALL_RAG_PROFILE:-0}" == "1" ]]; then
    requirements_file="${release}/requirements-rag.txt"
    fingerprint_files+=("${release}/requirements-rag.txt")
    log "Optional RAG dependency profile is enabled"
  fi

  python_version="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  requirements_hash="$({
    printf 'python=%s\n' "${python_version}"
    cat "${fingerprint_files[@]}"
  } | sha256sum | awk '{print $1}')"
  shared_venv="${VENV_ROOT}/py${python_version}-${requirements_hash:0:20}"

  if [[ ! -x "${shared_venv}/bin/python" ]]; then
    staging_venv="${VENV_ROOT}/.staging-${requirements_hash:0:20}-$$"
    rm -rf "${staging_venv}"
    log "Creating shared Python environment ${shared_venv}"
    "${PYTHON_BIN}" -m venv "${staging_venv}"
    PIP_CACHE_DIR="${CACHE_ROOT}/pip" \
      PIP_DISABLE_PIP_VERSION_CHECK=1 \
      PIP_PREFER_BINARY=1 \
      "${staging_venv}/bin/python" -m pip install --upgrade pip setuptools wheel
    PIP_CACHE_DIR="${CACHE_ROOT}/pip" \
      PIP_DISABLE_PIP_VERSION_CHECK=1 \
      PIP_PREFER_BINARY=1 \
      "${staging_venv}/bin/python" -m pip install --prefer-binary --no-input \
      -r "${requirements_file}"
    "${staging_venv}/bin/python" -m pip check
    mv "${staging_venv}" "${shared_venv}"
  else
    log "Reusing shared Python environment ${shared_venv}"
    "${shared_venv}/bin/python" -m pip check
  fi

  rm -rf "${release}/.venv"
  ln -s "${shared_venv}" "${release}/.venv"
  "${release}/.venv/bin/python" -m compileall -q \
    "${release}/alembic" "${release}/config" "${release}/src"
}

preflight_release() {
  local release="$1"
  validate_runtime_env
  log "Running runtime preflight for ${release}"
  run_as_app_in_release \
    "${release}" \
    "${release}/.venv/bin/python" -m src.ops.doctor --runtime
}

run_migrations() {
  local release="$1"
  [[ -f "${release}/alembic.ini" ]] || \
    fail "Release does not contain alembic.ini"
  [[ -x "${release}/.venv/bin/alembic" ]] || \
    fail "Release virtualenv does not contain Alembic"

  log "Applying Alembic migrations"
  run_as_app_in_release \
    "${release}" \
    "${release}/.venv/bin/alembic" upgrade head
}

replace_symlink() {
  local link_path="$1"
  local target="$2"
  local temporary="${link_path}.new.$$"
  rm -f "${temporary}"
  ln -s "${target}" "${temporary}"
  mv -Tf "${temporary}" "${link_path}"
}

activate_release() {
  local release="$1"
  local old_release=""
  old_release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
  if [[ -n "${old_release}" && -d "${old_release}" ]]; then
    replace_symlink "${PREVIOUS_LINK}" "${old_release}"
  fi
  replace_symlink "${CURRENT_LINK}" "${release}"
}

render_systemd_units_from_release() {
  local release="$1"
  local unit source target temporary
  [[ -d "${release}" ]] || fail "Release is unavailable: ${release}"

  for unit in "${SYSTEMD_UNITS[@]}"; do
    source="${release}/deploy/systemd/${unit}"
    [[ -f "${source}" ]] || fail "Release is missing systemd template: ${unit}"
  done

  install -d -m 0755 "${SYSTEMD_UNIT_DIR}"
  for unit in "${SYSTEMD_UNITS[@]}"; do
    source="${release}/deploy/systemd/${unit}"
    target="${SYSTEMD_UNIT_DIR}/${unit}"
    temporary="${target}.new.$$"
    rm -f "${temporary}"
    render_template "${source}" "${temporary}"
    chmod 0644 "${temporary}"
    mv -Tf "${temporary}" "${target}"
  done
  service_control daemon-reload
}

heartbeat_is_fresh() {
  local heartbeat_file="${HEARTBEAT_FILE:-/run/crop-forecast-bot/heartbeat}"
  [[ -x "${CURRENT_LINK}/.venv/bin/python" ]] || return 1
  (
    cd "${CURRENT_LINK}"
    "${CURRENT_LINK}/.venv/bin/python" \
      -m src.ops.heartbeat "${heartbeat_file}" --max-age 120
  )
}

restart_and_verify() {
  local attempt
  [[ "${HEALTHCHECK_ATTEMPTS}" =~ ^[1-9][0-9]*$ ]] || \
    fail "HEALTHCHECK_ATTEMPTS must be a positive integer"
  [[ "${HEALTHCHECK_INTERVAL_SECONDS}" =~ ^[0-9]+$ ]] || \
    fail "HEALTHCHECK_INTERVAL_SECONDS must be a non-negative integer"

  load_runtime_env
  rm -f "${HEARTBEAT_FILE:-/run/crop-forecast-bot/heartbeat}" || true
  service_control restart "${SERVICE_NAME}"

  for ((attempt = 1; attempt <= HEALTHCHECK_ATTEMPTS; attempt++)); do
    if service_control is-active --quiet "${SERVICE_NAME}" && heartbeat_is_fresh; then
      log "Service is active and heartbeat is current"
      return 0
    fi
    if service_control is-failed --quiet "${SERVICE_NAME}"; then
      break
    fi
    if (( HEALTHCHECK_INTERVAL_SECONDS > 0 )); then
      sleep "${HEALTHCHECK_INTERVAL_SECONDS}"
    fi
  done

  service_journal -u "${SERVICE_NAME}" -n 100 --no-pager >&2 || true
  return 1
}

restore_release_after_failed_activation() {
  local failed_release="$1"
  local previous_release="$2"
  local active_release=""

  if [[ -n "${previous_release}" && -d "${previous_release}" ]]; then
    warn "Release ${failed_release} failed health verification; restoring ${previous_release}"
    replace_symlink "${CURRENT_LINK}" "${previous_release}"
    render_systemd_units_from_release "${previous_release}" || return 1
    if restart_and_verify; then
      log "Previous release recovered successfully"
      return 0
    fi
    warn "Previous release also failed health verification"
    return 1
  fi

  warn "Release ${failed_release} failed and no previous release is available"
  active_release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
  if [[ "${active_release}" == "${failed_release}" ]]; then
    rm -f "${CURRENT_LINK}"
  fi
  service_control stop "${SERVICE_NAME}" >/dev/null 2>&1 || true
  return 1
}

backup_database() {
  local dsn backup_file temporary
  if [[ "${SKIP_DATABASE_BACKUP:-0}" == "1" ]]; then
    warn "Database backup was explicitly skipped"
    return 0
  fi

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
  mapfile -t backups < <(
    find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'database-*.dump' \
      -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-
  )
  for ((index = KEEP_BACKUPS; index < ${#backups[@]}; index++)); do
    rm -f "${backups[index]}"
  done
}

venv_is_referenced() {
  local candidate="$1"
  local link target
  for link in "${RELEASES_DIR}"/*/.venv; do
    [[ -L "${link}" ]] || continue
    target="$(readlink -f "${link}" 2>/dev/null || true)"
    [[ "${target}" == "${candidate}" ]] && return 0
  done
  return 1
}

prune_shared_venvs() {
  local candidate
  rm -rf "${VENV_ROOT}"/.staging-* 2>/dev/null || true
  for candidate in "${VENV_ROOT}"/*; do
    [[ -d "${candidate}" ]] || continue
    if ! venv_is_referenced "${candidate}"; then
      log "Removing unused shared Python environment ${candidate}"
      rm -rf "${candidate}"
    fi
  done
}

prune_releases() {
  local current previous index release
  local -a releases=()
  current="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
  previous="$(readlink -f "${PREVIOUS_LINK}" 2>/dev/null || true)"
  mapfile -t releases < <(
    find "${RELEASES_DIR}" -mindepth 1 -maxdepth 1 -type d ! -name '.staging-*' \
      -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-
  )

  for ((index = KEEP_RELEASES; index < ${#releases[@]}; index++)); do
    release="${releases[index]}"
    if [[ "${release}" == "${current}" || "${release}" == "${previous}" ]]; then
      continue
    fi
    log "Removing old release ${release}"
    rm -rf "${release}"
  done
  prune_shared_venvs
}

render_template() {
  local source="$1"
  local target="$2"
  sed \
    -e "s|@APP_USER@|${APP_USER}|g" \
    -e "s|@APP_GROUP@|${APP_GROUP}|g" \
    -e "s|@APP_ROOT@|${APP_ROOT}|g" \
    -e "s|@CURRENT_LINK@|${CURRENT_LINK}|g" \
    -e "s|@STATE_ROOT@|${STATE_ROOT}|g" \
    -e "s|@CACHE_ROOT@|${CACHE_ROOT}|g" \
    -e "s|@LOG_ROOT@|${LOG_ROOT}|g" \
    -e "s|@ENV_FILE@|${ENV_FILE}|g" \
    -e "s|@BRANCH@|${BRANCH}|g" \
    "${source}" > "${target}"
}
