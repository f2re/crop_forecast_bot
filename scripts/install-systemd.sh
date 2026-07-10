#!/usr/bin/env bash
set -Eeuo pipefail

[[ "${EUID}" -eq 0 ]] || { echo "Run as root" >&2; exit 1; }

APP_USER="${APP_USER:-cropbot}"
APP_DIR="${APP_DIR:-/opt/crop_forecast_bot}"
REPO_URL="${REPO_URL:-https://github.com/f2re/crop_forecast_bot.git}"
BRANCH="${BRANCH:-main}"
ENV_FILE="${ENV_FILE:-/etc/crop-forecast-bot.env}"

apt-get update
apt-get install -y --no-install-recommends \
  git python3 python3-venv python3-dev build-essential \
  libpq-dev gdal-bin libgdal-dev postgresql redis-server ca-certificates

id "${APP_USER}" >/dev/null 2>&1 || \
  useradd --system --create-home --home-dir "/var/lib/${APP_USER}" --shell /usr/sbin/nologin "${APP_USER}"

if [[ ! -d "${APP_DIR}/.git" ]]; then
  git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
else
  git -C "${APP_DIR}" fetch --prune origin "${BRANCH}"
  git -C "${APP_DIR}" checkout "${BRANCH}"
  git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
fi

python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip setuptools wheel
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

install -d -o "${APP_USER}" -g "${APP_USER}" \
  "${APP_DIR}/data/cache" "${APP_DIR}/data/literature" "${APP_DIR}/logs" /tmp/crop_forecast_bot

if [[ ! -f "${ENV_FILE}" ]]; then
  install -m 640 -o root -g "${APP_USER}" "${APP_DIR}/.env.example" "${ENV_FILE}"
  echo "Configuration created: ${ENV_FILE}" >&2
  echo "Set TELEGRAM_BOT_TOKEN, DATABASE_URL and REDIS_URL, then rerun this installer." >&2
  exit 2
fi

sed \
  -e "s|@APP_USER@|${APP_USER}|g" \
  -e "s|@APP_DIR@|${APP_DIR}|g" \
  -e "s|@ENV_FILE@|${ENV_FILE}|g" \
  "${APP_DIR}/deploy/systemd/crop-forecast-bot.service" \
  > /etc/systemd/system/crop-forecast-bot.service

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}/data" "${APP_DIR}/logs"
systemctl daemon-reload
systemctl enable redis-server postgresql crop-forecast-bot

preflight_command=$(cat <<EOF
set -a
source '${ENV_FILE}'
set +a
cd '${APP_DIR}'
exec '${APP_DIR}/.venv/bin/python' -m src.ops.doctor --runtime
EOF
)
if ! runuser -u "${APP_USER}" -- bash -c "${preflight_command}"; then
  echo "Preflight failed. Configure PostgreSQL/Redis and ${ENV_FILE}; service was not started." >&2
  exit 1
fi

systemctl restart crop-forecast-bot
systemctl --no-pager --full status crop-forecast-bot
