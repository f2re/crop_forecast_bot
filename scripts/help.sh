#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/crop-forecast-bot}"
CURRENT="${APP_ROOT}/current"

cat <<EOF
🌾 Crop Forecast Bot — справка

Telegram:
  /start   главное меню и активное поле
  /help    пользовательская справка
  /cancel  отменить текущий ввод

  Основной путь:
    Мои поля → культура → сезон/фаза → агроотчёт

Сервис:
  sudo systemctl status crop-forecast-bot
  sudo systemctl restart crop-forecast-bot
  sudo journalctl -u crop-forecast-bot -f

Диагностика:
  sudo bash ${CURRENT}/scripts/status.sh
  sudo -u cropbot ${CURRENT}/.venv/bin/python -m src.ops.doctor --runtime

Полная проверка release:
  sudo -u cropbot bash ${CURRENT}/scripts/verify-production.sh
  sudo -u cropbot bash ${CURRENT}/scripts/verify-production.sh \
    --live-provider 55.75 37.62 2026-04-15

Обновление и откат:
  sudo bash ${CURRENT}/scripts/update.sh main
  sudo bash ${CURRENT}/scripts/rollback.sh

Конфигурация:
  sudo editor /etc/crop-forecast-bot.env
  sudo systemctl restart crop-forecast-bot

База данных:
  sudo -u cropbot bash -lc 'cd ${CURRENT} && .venv/bin/alembic current'
  sudo -u cropbot bash -lc 'cd ${CURRENT} && .venv/bin/alembic heads'
  sudo -u cropbot bash -lc 'cd ${CURRENT} && .venv/bin/alembic upgrade head'

Опциональный RAG:
  INSTALL_RAG_PROFILE=1
  RAG_ENABLED=true
  sudo bash ${CURRENT}/scripts/update.sh main
  sudo -u cropbot bash -lc 'cd ${CURRENT} && .venv/bin/python -m src.knowledge.indexer --reset'
EOF
