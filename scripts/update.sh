#!/usr/bin/env bash
set -Eeuo pipefail

# Install a fresh release from Git, verify it, switch the current symlink
# atomically and restore the previous release if the service does not recover.

# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
acquire_deploy_lock
require_command git
require_command python3
require_command systemctl
require_command pg_dump

branch="${1:-${BRANCH}}"
old_release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
old_sha=""

[[ -n "${old_release}" && -d "${old_release}" ]] || \
  fail "No active release found. Run scripts/deploy.sh first."
old_sha="$(git -C "${old_release}" rev-parse HEAD)"

validate_runtime_env
prepare_runtime_directories
create_release "${branch}"

if [[ "${NEW_RELEASE_SHA}" == "${old_sha}" ]]; then
  rm -rf "${NEW_RELEASE}"
  log "Already running commit ${old_sha}; no update required"
  exit 0
fi

build_release "${NEW_RELEASE}"
preflight_release "${NEW_RELEASE}"
backup_database
run_migrations_if_available "${NEW_RELEASE}"

for unit in \
  crop-forecast-bot.service \
  crop-forecast-bot-update.service \
  crop-forecast-bot-update.timer; do
  [[ -f "${NEW_RELEASE}/deploy/systemd/${unit}" ]] || \
    fail "New release is missing systemd template: ${unit}"
  render_template \
    "${NEW_RELEASE}/deploy/systemd/${unit}" \
    "/etc/systemd/system/${unit}"
  chmod 0644 "/etc/systemd/system/${unit}"
done
systemctl daemon-reload

activate_release "${NEW_RELEASE}"
if ! restart_and_verify; then
  warn "Update failed health verification; rolling back to ${old_sha}"
  replace_symlink "${CURRENT_LINK}" "${old_release}"

  for unit in \
    crop-forecast-bot.service \
    crop-forecast-bot-update.service \
    crop-forecast-bot-update.timer; do
    if [[ -f "${old_release}/deploy/systemd/${unit}" ]]; then
      render_template \
        "${old_release}/deploy/systemd/${unit}" \
        "/etc/systemd/system/${unit}"
      chmod 0644 "/etc/systemd/system/${unit}"
    fi
  done
  systemctl daemon-reload

  if ! restart_and_verify; then
    fail "Both the new and previous releases failed; inspect journalctl -u ${SERVICE_NAME}"
  fi
  fail "Update was rolled back; database backup is available in ${BACKUP_ROOT}"
fi

prune_releases
log "Update completed: ${old_sha} -> ${NEW_RELEASE_SHA}"
