#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

log() {
  printf '[crop-forecast-bot] %s\n' "$*"
}

fail() {
  printf '[crop-forecast-bot] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

ensure_env_file() {
  if [[ ! -f .env ]]; then
    cp .env.example .env
    chmod 600 .env
    fail ".env was created from .env.example. Fill TELEGRAM_BOT_TOKEN and DB_PASSWORD, then rerun."
  fi

  grep -Eq '^TELEGRAM_BOT_TOKEN=.+$' .env || fail "TELEGRAM_BOT_TOKEN is empty in .env"
  grep -Eq '^DB_PASSWORD=.+$' .env || fail "DB_PASSWORD is empty in .env"
  if grep -Eq '^DB_PASSWORD=(change-me|postgres)$' .env; then
    fail "Replace the default DB_PASSWORD in .env"
  fi
}

compose() {
  docker compose "$@"
}
