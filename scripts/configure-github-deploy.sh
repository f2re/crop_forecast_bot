#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

REPOSITORY="${REPOSITORY:-f2re/crop_forecast_bot}"
DEPLOY_ENVIRONMENT="${DEPLOY_ENVIRONMENT:-production}"
DEPLOY_HOST="${DEPLOY_HOST:-}"
DEPLOY_PORT="${DEPLOY_PORT:-22}"
DEPLOY_USER="${DEPLOY_USER:-cropdeploy}"
DEPLOY_SSH_KEY_FILE="${DEPLOY_SSH_KEY_FILE:-}"
DEPLOY_KNOWN_HOSTS_FILE="${DEPLOY_KNOWN_HOSTS_FILE:-}"
ENABLE_TRIGGER="${ENABLE_TRIGGER:-true}"
RUN_TRIGGER_TEST="${RUN_TRIGGER_TEST:-false}"
GH_BIN="${GH_BIN:-gh}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

log() {
  printf '[github-deploy] %s\n' "$*" >&2
}

is_true() {
  case "${1:-false}" in
    true|1|yes|on) return 0 ;;
    false|0|no|off) return 1 ;;
    *) fail "boolean value expected, got: $1" ;;
  esac
}

require_value() {
  local name="$1"
  local value="$2"
  [[ -n "${value}" ]] || fail "${name} is required"
}

require_file() {
  local name="$1"
  local path="$2"
  require_value "${name}" "${path}"
  [[ -r "${path}" ]] || fail "${name} is not readable: ${path}"
  [[ -s "${path}" ]] || fail "${name} is empty: ${path}"
}

file_mode() {
  local path="$1"
  if stat -c '%a' "${path}" >/dev/null 2>&1; then
    stat -c '%a' "${path}"
    return
  fi
  if stat -f '%Lp' "${path}" >/dev/null 2>&1; then
    stat -f '%Lp' "${path}"
    return
  fi
  fail "cannot determine file mode for ${path}"
}

command -v "${GH_BIN}" >/dev/null 2>&1 || \
  fail "GitHub CLI is required: https://cli.github.com/"
"${GH_BIN}" auth status >/dev/null 2>&1 || \
  fail "GitHub CLI is not authenticated; run: gh auth login"

[[ "${REPOSITORY}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || \
  fail "REPOSITORY must use owner/name format"
[[ "${DEPLOY_ENVIRONMENT}" =~ ^[A-Za-z0-9_.-]+$ ]] || \
  fail "DEPLOY_ENVIRONMENT contains unsupported characters"
[[ "${DEPLOY_PORT}" =~ ^[0-9]{1,5}$ ]] || \
  fail "DEPLOY_PORT must be an integer between 1 and 65535"
(( DEPLOY_PORT >= 1 && DEPLOY_PORT <= 65535 )) || \
  fail "DEPLOY_PORT must be between 1 and 65535"
require_value "DEPLOY_HOST" "${DEPLOY_HOST}"
require_value "DEPLOY_USER" "${DEPLOY_USER}"
require_file "DEPLOY_SSH_KEY_FILE" "${DEPLOY_SSH_KEY_FILE}"
require_file "DEPLOY_KNOWN_HOSTS_FILE" "${DEPLOY_KNOWN_HOSTS_FILE}"

private_key_mode="$(file_mode "${DEPLOY_SSH_KEY_FILE}")"
case "${private_key_mode}" in
  400|600) ;;
  *) fail "DEPLOY_SSH_KEY_FILE must have mode 0400 or 0600" ;;
esac

grep -Eq '^[^#[:space:]].*[[:space:]](ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp)' \
  "${DEPLOY_KNOWN_HOSTS_FILE}" || \
  fail "DEPLOY_KNOWN_HOSTS_FILE does not contain a recognizable host key"

export GH_PROMPT_DISABLED=1
log "Creating or updating GitHub environment ${DEPLOY_ENVIRONMENT}"
"${GH_BIN}" api \
  --method PUT \
  "repos/${REPOSITORY}/environments/${DEPLOY_ENVIRONMENT}" \
  >/dev/null

log "Writing protected environment secrets"
printf '%s' "${DEPLOY_HOST}" | \
  "${GH_BIN}" secret set DEPLOY_HOST \
    --repo "${REPOSITORY}" --env "${DEPLOY_ENVIRONMENT}"
printf '%s' "${DEPLOY_PORT}" | \
  "${GH_BIN}" secret set DEPLOY_PORT \
    --repo "${REPOSITORY}" --env "${DEPLOY_ENVIRONMENT}"
printf '%s' "${DEPLOY_USER}" | \
  "${GH_BIN}" secret set DEPLOY_USER \
    --repo "${REPOSITORY}" --env "${DEPLOY_ENVIRONMENT}"
"${GH_BIN}" secret set DEPLOY_SSH_KEY \
  --repo "${REPOSITORY}" --env "${DEPLOY_ENVIRONMENT}" \
  < "${DEPLOY_SSH_KEY_FILE}"
"${GH_BIN}" secret set DEPLOY_KNOWN_HOSTS \
  --repo "${REPOSITORY}" --env "${DEPLOY_ENVIRONMENT}" \
  < "${DEPLOY_KNOWN_HOSTS_FILE}"

if is_true "${ENABLE_TRIGGER}"; then
  trigger_value=true
else
  trigger_value=false
fi
log "Setting repository deployment flag to ${trigger_value}"
"${GH_BIN}" variable set DEPLOY_TRIGGER_ENABLED \
  --repo "${REPOSITORY}" --body "${trigger_value}"

secret_names="$(
  "${GH_BIN}" secret list \
    --repo "${REPOSITORY}" --env "${DEPLOY_ENVIRONMENT}" \
    --json name --jq '.[].name'
)"
for required_secret in \
  DEPLOY_HOST DEPLOY_PORT DEPLOY_USER DEPLOY_SSH_KEY DEPLOY_KNOWN_HOSTS; do
  grep -qx "${required_secret}" <<<"${secret_names}" || \
    fail "GitHub did not report environment secret ${required_secret}"
done

actual_flag="$(
  "${GH_BIN}" variable get DEPLOY_TRIGGER_ENABLED \
    --repo "${REPOSITORY}" --json value --jq '.value'
)"
[[ "${actual_flag}" == "${trigger_value}" ]] || \
  fail "DEPLOY_TRIGGER_ENABLED verification failed"

if is_true "${RUN_TRIGGER_TEST}"; then
  [[ "${trigger_value}" == "true" ]] || \
    fail "RUN_TRIGGER_TEST requires ENABLE_TRIGGER=true"
  log "Starting manual deployment-trigger verification"
  "${GH_BIN}" workflow run deploy-production.yml \
    --repo "${REPOSITORY}" --ref main
fi

log "GitHub deployment trigger configuration is complete"
log "Repository: ${REPOSITORY}"
log "Environment: ${DEPLOY_ENVIRONMENT}"
log "Enabled: ${trigger_value}"
if ! is_true "${RUN_TRIGGER_TEST}"; then
  log "Manual verification: gh workflow run deploy-production.yml --repo ${REPOSITORY} --ref main"
fi
