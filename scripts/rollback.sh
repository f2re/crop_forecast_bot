#!/usr/bin/env bash
set -Eeuo pipefail

# Roll back application code and the matching systemd units to the previous
# (or explicitly selected) release. Database migrations are not reversed.

# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
acquire_deploy_lock
validate_runtime_env

current_release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
target_release="${1:-$(readlink -f "${PREVIOUS_LINK}" 2>/dev/null || true)}"

[[ -n "${current_release}" && -d "${current_release}" ]] || \
  fail "Current release is unavailable"
[[ -n "${target_release}" && -d "${target_release}" ]] || \
  fail "Rollback target is unavailable"

case "${target_release}" in
  "${RELEASES_DIR}"/*) ;;
  *) fail "Rollback target must be inside ${RELEASES_DIR}" ;;
esac

[[ "${target_release}" != "${current_release}" ]] || \
  fail "Rollback target is already active"
[[ -x "${target_release}/.venv/bin/python" ]] || \
  fail "Rollback target has no Python environment"

preflight_release "${target_release}"
render_systemd_units_from_release "${target_release}"
replace_symlink "${PREVIOUS_LINK}" "${current_release}"
replace_symlink "${CURRENT_LINK}" "${target_release}"

if ! restart_and_verify; then
  if restore_release_after_failed_activation "${target_release}" "${current_release}"; then
    fail "Rollback target failed health verification; original release was restored"
  fi
  fail "Rollback target and original release both failed health verification"
fi

log "Rollback completed: $(git -C "${current_release}" rev-parse HEAD) -> $(git -C "${target_release}" rev-parse HEAD)"
