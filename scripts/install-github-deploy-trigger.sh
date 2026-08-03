#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

DEPLOY_USER="${DEPLOY_USER:-cropdeploy}"
DEPLOY_HOME="${DEPLOY_HOME:-/var/lib/crop-forecast-deploy}"
TRIGGER_SCRIPT="${TRIGGER_SCRIPT:-/usr/local/sbin/crop-forecast-bot-trigger-update}"
SUDOERS_FILE="${SUDOERS_FILE:-/etc/sudoers.d/crop-forecast-bot-deploy}"
SERVICE_NAME="${SERVICE_NAME:-crop-forecast-bot-update.service}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "run as root"
[[ "$#" -eq 1 ]] || fail "usage: $0 /path/to/github-deploy-key.pub"
[[ -r "$1" ]] || fail "public key file is not readable: $1"

SYSTEMCTL_BIN="$(command -v systemctl)" || fail "systemctl is required"
SUDO_BIN="$(command -v sudo)" || fail "sudo is required"
VISUDO_BIN="$(command -v visudo)" || fail "visudo is required"

mapfile -t key_lines < <(
  grep -Ev '^[[:space:]]*(#|$)' "$1" | sed 's/[[:space:]]*$//'
)
[[ "${#key_lines[@]}" -eq 1 ]] || fail "public key file must contain one key"
PUBLIC_KEY="${key_lines[0]}"
case "${PUBLIC_KEY}" in
  ssh-ed25519\ *|sk-ssh-ed25519@openssh.com\ *|ssh-rsa\ *) ;;
  *) fail "unsupported or malformed OpenSSH public key" ;;
esac

if ! id -u "${DEPLOY_USER}" >/dev/null 2>&1; then
  useradd \
    --system \
    --user-group \
    --create-home \
    --home-dir "${DEPLOY_HOME}" \
    --shell /bin/sh \
    "${DEPLOY_USER}"
else
  usermod --home "${DEPLOY_HOME}" --shell /bin/sh "${DEPLOY_USER}"
  install -d -m 0750 -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${DEPLOY_HOME}"
fi
passwd -l "${DEPLOY_USER}" >/dev/null 2>&1 || true

trigger_tmp="$(mktemp)"
sudoers_tmp="$(mktemp)"
cleanup() {
  rm -f "${trigger_tmp}" "${sudoers_tmp}"
}
trap cleanup EXIT

cat > "${trigger_tmp}" <<EOF
#!/bin/sh
set -eu
exec ${SUDO_BIN} -n ${SYSTEMCTL_BIN} --no-block start ${SERVICE_NAME}
EOF
install -o root -g root -m 0755 "${trigger_tmp}" "${TRIGGER_SCRIPT}"

printf '%s ALL=(root) NOPASSWD: %s --no-block start %s\n' \
  "${DEPLOY_USER}" "${SYSTEMCTL_BIN}" "${SERVICE_NAME}" > "${sudoers_tmp}"
"${VISUDO_BIN}" -cf "${sudoers_tmp}" >/dev/null
install -o root -g root -m 0440 "${sudoers_tmp}" "${SUDOERS_FILE}"

SSH_DIR="${DEPLOY_HOME}/.ssh"
AUTHORIZED_KEYS="${SSH_DIR}/authorized_keys"
install -d -m 0700 -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${SSH_DIR}"
printf 'restrict,command="%s" %s\n' "${TRIGGER_SCRIPT}" "${PUBLIC_KEY}" \
  > "${AUTHORIZED_KEYS}"
chown "${DEPLOY_USER}:${DEPLOY_USER}" "${AUTHORIZED_KEYS}"
chmod 0600 "${AUTHORIZED_KEYS}"

printf 'Restricted GitHub deployment trigger installed.\n'
printf 'User: %s\n' "${DEPLOY_USER}"
printf 'Service: %s\n' "${SERVICE_NAME}"
printf 'Authorized key: %s\n' "${AUTHORIZED_KEYS}"
printf 'The existing systemd timer remains the fallback update path.\n'
