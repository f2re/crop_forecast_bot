#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  if [[ -x .venv/bin/python ]]; then
    PYTHON=.venv/bin/python
  elif [[ -x /opt/crop-forecast-bot/current/.venv/bin/python ]]; then
    PYTHON=/opt/crop-forecast-bot/current/.venv/bin/python
  else
    PYTHON=python3
  fi
fi

log() {
  printf '[verify-production] %s\n' "$*"
}

log "Checking forbidden deployment artifacts"
test ! -e Dockerfile
test ! -e docker-compose.yml
test ! -e .env.docker.example

log "Compiling all Python modules"
"${PYTHON}" -m compileall -q alembic config src tests

if "${PYTHON}" -m ruff --version >/dev/null 2>&1; then
  log "Running ruff over the full Python tree"
  "${PYTHON}" -m ruff check src config alembic tests
fi

if "${PYTHON}" -m pytest --version >/dev/null 2>&1; then
  log "Running the complete test suite"
  "${PYTHON}" -m pytest -q
fi

if command -v shellcheck >/dev/null 2>&1; then
  log "Checking native Bash scripts"
  bash -n scripts/*.sh
  shellcheck -x \
    scripts/deploy.sh \
    scripts/update.sh \
    scripts/rollback.sh \
    scripts/status.sh \
    scripts/help.sh \
    scripts/install-systemd.sh \
    scripts/smoke-provider.sh \
    scripts/verify-production.sh
fi

if [[ -f alembic.ini ]] && "${PYTHON}" -m alembic --help >/dev/null 2>&1; then
  log "Checking Alembic head"
  "${PYTHON}" -m alembic heads
fi

if [[ "${1:-}" == "--live-provider" ]]; then
  log "Running live Open-Meteo contract smoke check"
  bash scripts/smoke-provider.sh "${2:-55.75}" "${3:-37.62}" "${4:-}"
fi

log "Verification completed"
