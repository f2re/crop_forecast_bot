#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/crop-forecast-bot}"
CURRENT="${APP_ROOT}/current"

cat <<EOF
🌾 Crop Forecast Bot — справка MVP

Telegram:
  /start    главное меню и активное поле
  /risks    ручной обзор ансамблевых рисков
  /history  история и изменение сигналов
  /help     пользовательская справка
  /cancel   отменить текущий ввод

  Основной путь:
    Мои поля → культура → сезон/фаза → агроотчёт/риски

  Фоновый мониторинг:
    после запуска проверяются все сохранённые поля с включёнными alerts;
    затем ансамблевый цикл выполняется каждые 6 часов.

Сервис:
  sudo systemctl status crop-forecast-bot
  sudo systemctl restart crop-forecast-bot
  sudo journalctl -u crop-forecast-bot -f

Диагностика:
  sudo bash ${CURRENT}/scripts/status.sh
  sudo -u cropbot ${CURRENT}/.venv/bin/python -m src.ops.doctor --runtime

Production startup-smoke без Telegram-сети:
  sudo -u cropbot bash -lc \
    'cd ${CURRENT} && .venv/bin/python -m src.bot.main --startup-smoke'

Полная проверка release:
  sudo -u cropbot bash ${CURRENT}/scripts/verify-production.sh
  sudo -u cropbot bash ${CURRENT}/scripts/verify-production.sh \
    --live-all 55.75 37.62 2026-04-15 wheat

Автоматическое обновление:
  sudo systemctl list-timers crop-forecast-bot-update.timer
  sudo systemctl status crop-forecast-bot-update.timer
  sudo journalctl -u crop-forecast-bot-update -f

  Timer проверяет main каждые 15 минут. Новый SHA устанавливается только
  после зелёного GitHub Actions CI. Pending/failed/API error оставляет
  текущий release работающим.

Ручная проверка обновления и откат:
  sudo systemctl start crop-forecast-bot-update.service
  sudo bash ${CURRENT}/scripts/update.sh main
  sudo bash ${CURRENT}/scripts/rollback.sh

Конфигурация:
  sudo editor /etc/crop-forecast-bot.env
  sudo systemctl restart crop-forecast-bot

База данных:
  sudo -u cropbot bash -lc 'cd ${CURRENT} && .venv/bin/python -m alembic current'
  sudo -u cropbot bash -lc 'cd ${CURRENT} && .venv/bin/python -m alembic heads'
  sudo -u cropbot bash -lc 'cd ${CURRENT} && .venv/bin/python -m alembic upgrade head'
  sudo bash ${CURRENT}/scripts/verify-backup-restore.sh

Ресурсный профиль по умолчанию:
  BLOCKING_IO_WORKERS=2
  RISK_HISTORY_RETENTION_DAYS=30
  CLIMATE_REFERENCE_ENABLED=false
  RAG_ENABLED=false

Опциональный climate reference:
  CLIMATE_REFERENCE_ENABLED=true
  sudo systemctl restart crop-forecast-bot

Опциональный RAG:
  INSTALL_RAG_PROFILE=1
  RAG_ENABLED=true
  sudo bash ${CURRENT}/scripts/update.sh main
  sudo -u cropbot bash -lc \
    'cd ${CURRENT} && .venv/bin/python -m src.knowledge.indexer --reset'

Подробно:
  ${CURRENT}/docs/LOW_RESOURCE_MVP.md
EOF
