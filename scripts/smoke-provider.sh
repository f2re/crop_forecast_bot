#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/crop-forecast-bot}"
CURRENT="${APP_ROOT}/current"
LATITUDE="${1:-55.75}"
LONGITUDE="${2:-37.62}"
SEASON_START="${3:-}"

if [[ -x "${CURRENT}/.venv/bin/python" ]]; then
  PYTHON="${CURRENT}/.venv/bin/python"
  cd "${CURRENT}"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  echo "Python virtual environment was not found" >&2
  exit 1
fi

args=(
  -m src.ops.provider_smoke
  --latitude "${LATITUDE}"
  --longitude "${LONGITUDE}"
)
if [[ -n "${SEASON_START}" ]]; then
  args+=(--season-start "${SEASON_START}")
fi

exec "${PYTHON}" "${args[@]}"
