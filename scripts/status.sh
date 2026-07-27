#!/usr/bin/env bash
set -Eeuo pipefail

# Display service state, active/previous releases, unit consistency, heartbeat,
# update timer, runtime dependencies and recent service diagnostics.

# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
validate_runtime_env
require_command cmp

current_release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
previous_release="$(readlink -f "${PREVIOUS_LINK}" 2>/dev/null || true)"
[[ -n "${current_release}" && -d "${current_release}" ]] || \
  fail "No active release found"

printf 'Service:              %s\n' "${SERVICE_NAME}"
printf 'Service active:       %s\n' "$(service_control is-active "${SERVICE_NAME}" 2>/dev/null || true)"
printf 'Service enabled:      %s\n' "$(service_control is-enabled "${SERVICE_NAME}" 2>/dev/null || true)"
printf 'Release:              %s\n' "${current_release}"
printf 'Commit:               %s\n' "$(git -C "${current_release}" rev-parse HEAD)"
printf 'Previous:             %s\n' "${previous_release:-unavailable}"
printf 'Update timer active:  %s\n' "$(service_control is-active "${UPDATE_TIMER_NAME}" 2>/dev/null || true)"
printf 'Update timer enabled: %s\n' "$(service_control is-enabled "${UPDATE_TIMER_NAME}" 2>/dev/null || true)"
printf 'Auto-update config:   %s\n' "${AUTO_UPDATE_ENABLED:-true}"
printf 'Green-CI gate:        %s\n' "${AUTO_UPDATE_REQUIRE_GREEN_CI:-true}"

if heartbeat_is_fresh; then
  printf 'Heartbeat:            healthy\n'
else
  printf 'Heartbeat:            stale or unavailable\n'
fi

unit_state="matches active release"
for unit in "${SYSTEMD_UNITS[@]}"; do
  expected="$(mktemp)"
  render_template "${current_release}/deploy/systemd/${unit}" "${expected}"
  if [[ ! -f "${SYSTEMD_UNIT_DIR}/${unit}" ]] || \
     ! cmp -s "${expected}" "${SYSTEMD_UNIT_DIR}/${unit}"; then
    unit_state="MISMATCH: ${unit}"
    rm -f "${expected}"
    break
  fi
  rm -f "${expected}"
done
printf 'Unit files:           %s\n' "${unit_state}"

latest_backup="$(
  find "${BACKUP_ROOT}" -maxdepth 1 -type f -name 'database-*.dump' \
    -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2-
)"
printf 'Latest backup:        %s\n' "${latest_backup:-unavailable}"

printf '\nRuntime preflight:\n'
run_as_app_in_release \
  "${current_release}" \
  "${current_release}/.venv/bin/python" -m src.ops.doctor --runtime

printf '\nUpdate timer schedule:\n'
service_control list-timers "${UPDATE_TIMER_NAME}" --no-pager 2>/dev/null || true

printf '\nRecent service log:\n'
service_journal -u "${SERVICE_NAME}" -n "${JOURNAL_LINES:-60}" --no-pager

printf '\nRecent update log:\n'
service_journal -u "crop-forecast-bot-update.service" -n 30 --no-pager || true

[[ "${unit_state}" == "matches active release" ]] || \
  fail "Installed systemd units do not match the active release"
