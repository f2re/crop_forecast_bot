#!/usr/bin/env bash
set -Eeuo pipefail

# Install a fresh release from Git, verify it, switch the current symlink
# atomically and restore the previous release and unit files on failure.

# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
acquire_deploy_lock
require_command git
require_command python3
require_command "${SYSTEMCTL_BIN}"
require_command pg_dump

BRANCH="${1:-${BRANCH}}"
old_release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
old_sha=""

[[ -n "${old_release}" && -d "${old_release}" ]] || \
  fail "No active release found. Run scripts/deploy.sh first."
old_sha="$(git -C "${old_release}" rev-parse HEAD)"

validate_runtime_env
prepare_runtime_directories
create_release "${BRANCH}"

if [[ "${NEW_RELEASE_SHA}" == "${old_sha}" ]]; then
  rm -rf "${NEW_RELEASE}"
  log "Already running commit ${old_sha}; no update required"
  exit 0
fi

build_release "${NEW_RELEASE}"
backup_database
run_migrations "${NEW_RELEASE}"
preflight_release "${NEW_RELEASE}"
render_systemd_units_from_release "${NEW_RELEASE}"
activate_release "${NEW_RELEASE}"

if ! restart_and_verify; then
  if restore_release_after_failed_activation "${NEW_RELEASE}" "${old_release}"; then
    fail "Update was rolled back; database backup is available in ${BACKUP_ROOT}"
  fi
  fail "Both the new and previous releases failed; inspect the service journal"
fi

prune_releases
log "Update completed: ${old_sha} -> ${NEW_RELEASE_SHA}"
