#!/usr/bin/env bash
set -Eeuo pipefail

# Register or verify Telegram slash commands for the installed release.
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
validate_runtime_env

release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
[[ -n "${release}" && -d "${release}" ]] || \
  fail "No active release found. Run scripts/deploy.sh first."
[[ -x "${release}/.venv/bin/python" ]] || \
  fail "Active release has no executable Python environment"

mode="${1:---check}"
case "${mode}" in
  --check|--apply|--botfather) ;;
  *) fail "Usage: $0 [--check|--apply|--botfather]" ;;
esac

run_as_app_in_release \
  "${release}" \
  "${release}/.venv/bin/python" -m src.ops.telegram_commands "${mode}"
