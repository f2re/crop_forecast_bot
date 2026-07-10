#!/usr/bin/env bash
set -Eeuo pipefail

# Backward-compatible entrypoint. The complete native installation now lives
# in deploy.sh so deployment behavior cannot diverge between scripts.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/deploy.sh" "$@"
