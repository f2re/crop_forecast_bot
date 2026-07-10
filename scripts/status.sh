#!/usr/bin/env bash
set -Eeuo pipefail

# Display service state, active release, heartbeat and dependency diagnostics.

# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
validate_runtime_env

current_release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
[[ -n "${current_release}" && -d "${current_release}" ]] || \
  fail "No active release found"

printf 'Service:       %s\n' "${SERVICE_NAME}"
printf 'Active:        %s\n' "$(systemctl is-active "${SERVICE_NAME}" 2>/dev/null || true)"
printf 'Enabled:       %s\n' "$(systemctl is-enabled "${SERVICE_NAME}" 2>/dev/null || true)"
printf 'Release:       %s\n' "${current_release}"
printf 'Commit:        %s\n' "$(git -C "${current_release}" rev-parse HEAD)"
printf 'Update timer:  %s\n' "$(systemctl is-enabled "${UPDATE_TIMER_NAME}" 2>/dev/null || true)"

if heartbeat_is_fresh; then
  printf 'Heartbeat:     healthy\n'
else
  printf 'Heartbeat:     stale or unavailable\n'
fi

printf '\nRuntime preflight:\n'
run_as_app_in_release \
  "${current_release}" \
  "${current_release}/.venv/bin/python" -m src.ops.doctor --runtime

printf '\nRecent service log:\n'
journalctl -u "${SERVICE_NAME}" -n "${JOURNAL_LINES:-60}" --no-pager
