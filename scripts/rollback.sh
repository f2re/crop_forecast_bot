#!/usr/bin/env bash
set -Eeuo pipefail

# Roll back application code to the previous (or explicitly selected) release.
# Database migrations are not reversed automatically.

# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
acquire_deploy_lock
validate_runtime_env

render_units_from_release() {
  local release="$1"
  local unit
  for unit in \
    crop-forecast-bot.service \
    crop-forecast-bot-update.service \
    crop-forecast-bot-update.timer; do
    [[ -f "${release}/deploy/systemd/${unit}" ]] || \
      fail "Release is missing systemd template: ${unit}"
    render_template \
      "${release}/deploy/systemd/${unit}" \
      "/etc/systemd/system/${unit}"
    chmod 0644 "/etc/systemd/system/${unit}"
  done
  systemctl daemon-reload
}

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
render_units_from_release "${target_release}"
replace_symlink "${PREVIOUS_LINK}" "${current_release}"
replace_symlink "${CURRENT_LINK}" "${target_release}"

if ! restart_and_verify; then
  warn "Rollback target failed; restoring the original release"
  replace_symlink "${CURRENT_LINK}" "${current_release}"
  render_units_from_release "${current_release}"
  restart_and_verify || \
    fail "Original release also failed; inspect journalctl -u ${SERVICE_NAME}"
  fail "Rollback target failed health verification"
fi

log "Rollback completed: $(git -C "${current_release}" rev-parse HEAD) -> $(git -C "${target_release}" rev-parse HEAD)"
