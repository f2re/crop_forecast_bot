#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"

require_command docker
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 plugin is required"
ensure_env_file

log "Building application image"
compose build --pull bot

log "Starting PostgreSQL, Redis and bot"
compose up -d --remove-orphans

log "Checking service state"
compose ps

container_id="$(compose ps -q bot)"
[[ -n "${container_id}" ]] || fail "Bot container was not created"

status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}")"
if [[ "${status}" == "unhealthy" || "${status}" == "exited" || "${status}" == "dead" ]]; then
  compose logs --tail=200 bot >&2
  fail "Bot container state: ${status}"
fi

log "Deployment command completed; current bot state: ${status}"
