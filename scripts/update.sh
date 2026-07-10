#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "$0")/common.sh"

require_command git
require_command docker
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 plugin is required"
ensure_env_file

branch="${1:-main}"
backup_dir="${PROJECT_ROOT}/.deploy-backups"
mkdir -p "${backup_dir}"
cp .env "${backup_dir}/env-$(date +%Y%m%d-%H%M%S)"
previous_commit="$(git rev-parse HEAD)"

log "Fetching branch ${branch}"
git fetch --prune origin "${branch}"
git checkout "${branch}"
git pull --ff-only origin "${branch}"

if ! bash scripts/deploy.sh; then
  log "Deployment failed. Code remains at $(git rev-parse HEAD); previous commit was ${previous_commit}."
  log "Inspect logs with: docker compose logs --tail=300 bot"
  exit 1
fi

log "Update completed: ${previous_commit} -> $(git rev-parse HEAD)"
