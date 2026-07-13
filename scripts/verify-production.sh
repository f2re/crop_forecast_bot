#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

log() { printf '[verify] %s\n' "$*"; }
require_command() { command -v "$1" >/dev/null 2>&1 || { printf '[verify] ERROR: required command not found: %s\n' "$1" >&2; exit 1; }; }
usage() {
  cat >&2 <<EOF
Usage:
  $0
  $0 --live-provider LATITUDE LONGITUDE [SEASON_START]
  $0 --live-climate LATITUDE LONGITUDE SEASON_START [CROP]
  $0 --live-all LATITUDE LONGITUDE SEASON_START [CROP]
EOF
}

LIVE_MODE="none"
LATITUDE=""
LONGITUDE=""
SEASON_START=""
CROP="wheat"
case "${1:-}" in
  "")
    [[ $# -eq 0 ]] || { usage; exit 2; }
    ;;
  --live-provider)
    [[ $# -ge 3 && $# -le 4 ]] || { usage; exit 2; }
    LIVE_MODE="provider"
    LATITUDE="$2"
    LONGITUDE="$3"
    SEASON_START="${4:-}"
    ;;
  --live-climate|--live-all)
    [[ $# -ge 4 && $# -le 5 ]] || { usage; exit 2; }
    LIVE_MODE="${1#--live-}"
    LATITUDE="$2"
    LONGITUDE="$3"
    SEASON_START="$4"
    CROP="${5:-wheat}"
    ;;
  *)
    usage
    exit 2
    ;;
esac

require_command "${PYTHON_BIN}"

log "Checking forbidden deployment and legacy runtime artifacts"
for path in Dockerfile docker-compose.yml .env.docker.example main.py run_bot.py \
  scripts/train_basic_model.py scripts/deploy_to_platform.sh src/bot/simple_recommender.py; do
  [[ ! -e "${path}" ]] || { echo "[verify] ERROR: forbidden artifact exists: ${path}" >&2; exit 1; }
done

log "Running Ruff"
"${PYTHON_BIN}" -m ruff check src config alembic tests
log "Compiling Python modules"
"${PYTHON_BIN}" -m compileall -q alembic config src tests
log "Running unit and contract tests"
"${PYTHON_BIN}" -m pytest -q
log "Checking Alembic head"
"${PYTHON_BIN}" -m alembic heads
log "Checking Bash syntax"
bash -n scripts/*.sh

if command -v shellcheck >/dev/null 2>&1; then
  log "Running shellcheck"
  shellcheck -x scripts/common.sh scripts/deploy.sh scripts/update.sh \
    scripts/rollback.sh scripts/status.sh scripts/help.sh \
    scripts/install-systemd.sh scripts/verify-production.sh \
    scripts/verify-backup-restore.sh
else
  log "shellcheck is not installed; Bash syntax was checked"
fi

if [[ "${LIVE_MODE}" == "provider" || "${LIVE_MODE}" == "all" ]]; then
  log "Running read-only Open-Meteo operational contract smoke"
  command=(
    "${PYTHON_BIN}" -m src.ops.provider_smoke
    --latitude "${LATITUDE}"
    --longitude "${LONGITUDE}"
  )
  if [[ -n "${SEASON_START}" ]]; then command+=(--season-start "${SEASON_START}"); fi
  "${command[@]}"
fi

if [[ "${LIVE_MODE}" == "climate" || "${LIVE_MODE}" == "all" ]]; then
  log "Running read-only homogeneous ERA5-Land contract smoke"
  "${PYTHON_BIN}" -m src.ops.climate_smoke \
    --latitude "${LATITUDE}" \
    --longitude "${LONGITUDE}" \
    --season-start "${SEASON_START}" \
    --crop "${CROP}"
fi

log "All requested checks passed"
