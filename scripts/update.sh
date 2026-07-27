#!/usr/bin/env bash
set -Eeuo pipefail

# Pull-based CD for weak servers: check the remote SHA cheaply, require a green
# GitHub Actions result, then build and atomically activate exactly that commit.

# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

require_root
acquire_deploy_lock
require_command git
require_command "${PYTHON_BIN}"
require_command "${SYSTEMCTL_BIN}"
require_command pg_dump

BRANCH="${1:-${BRANCH}}"
old_release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"
old_sha=""
remote_sha=""

schema_revision_for_release() {
  local release="$1"
  run_as_app_in_release \
    "${release}" \
    "${release}/.venv/bin/python" -c \
    'from src.database.schema import expected_schema_revision; print(expected_schema_revision())'
}

[[ -n "${old_release}" && -d "${old_release}" ]] || \
  fail "No active release found. Run scripts/deploy.sh first."
old_sha="$(git -C "${old_release}" rev-parse HEAD)"

validate_runtime_env
prepare_runtime_directories

if ! remote_sha="$(remote_branch_sha "${BRANCH}")"; then
  warn "Remote branch ${BRANCH} is unavailable; keeping ${old_sha}"
  exit 0
fi
if [[ "${remote_sha}" == "${old_sha}" ]]; then
  log "Already running commit ${old_sha}; no update required"
  exit 0
fi

if [[ "${BRANCH}" == "main" ]] && \
   is_true_value "${AUTO_UPDATE_REQUIRE_GREEN_CI:-true}"; then
  log "Checking GitHub Actions release gate for ${remote_sha:0:12}"
  if run_as_app_in_release \
    "${old_release}" \
    "${old_release}/.venv/bin/python" -m src.ops.release_gate \
      --repository "${GITHUB_REPOSITORY}" \
      --branch "${BRANCH}" \
      --sha "${remote_sha}"; then
    log "GitHub Actions release gate passed"
  else
    gate_status=$?
    warn "Commit ${remote_sha:0:12} is not deployable yet (gate ${gate_status}); keeping ${old_sha:0:12}"
    exit 0
  fi
fi

create_release "${BRANCH}"
if [[ "${NEW_RELEASE_SHA}" != "${remote_sha}" ]]; then
  warn "Branch ${BRANCH} advanced during the check; discarding unverified release ${NEW_RELEASE_SHA:0:12}"
  rm -rf "${NEW_RELEASE}"
  exit 0
fi

build_release "${NEW_RELEASE}"
old_schema_revision="$(schema_revision_for_release "${old_release}")"
new_schema_revision="$(schema_revision_for_release "${NEW_RELEASE}")"
if [[ "${old_schema_revision}" != "${new_schema_revision}" ]] || \
   is_true_value "${FORCE_DATABASE_BACKUP:-false}"; then
  backup_database
else
  log "Alembic head is unchanged (${new_schema_revision}); skipping pre-update backup"
fi
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
