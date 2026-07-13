# 🚀 Быстрый старт и эксплуатация

Нативная установка Crop Forecast Bot на Debian 12, Ubuntu Server и совместимые Astra Linux окружения. Docker не нужен.

## 1. Подготовка

Нужны root-доступ, исходящий HTTPS к GitHub, Telegram и Open-Meteo, а также токен от `@BotFather`. Для core-профиля рекомендуется от 2 ГБ RAM.

```bash
sudo install -m 600 /dev/null /root/cropbot-token
sudo editor /root/cropbot-token
```

## 2. Первая установка

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

Скрипт создаёт пользователя `cropbot`, PostgreSQL/Redis, защищённый `/etc/crop-forecast-bot.env`, отдельный release и virtualenv, выполняет backup, Alembic migration, preflight и проверяет systemd heartbeat.

Systemd-unit устанавливаются из того же release, который активируется. Если новый release не проходит healthcheck, предыдущие код и unit-файлы восстанавливаются вместе и повторно проверяются по `active + heartbeat`.

## 3. Проверка сервиса

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
sudo journalctl -u crop-forecast-bot -n 100 --no-pager
```

Ожидается:

- service `active`;
- heartbeat `healthy`;
- PostgreSQL и Redis доступны;
- Alembic revision совпадает с head.

## 4. Полная проверка release

```bash
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh
```

Полный read-only smoke оперативного Open-Meteo и однородного ERA5-Land:

```bash
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh \
  --live-all 55.75 37.62 2026-04-15 wheat
```

Раздельные варианты:

```bash
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh \
  --live-provider 55.75 37.62 2026-04-15

sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh \
  --live-climate 55.75 37.62 2026-04-15 wheat
```

Проверяются структура ответа, локальные даты, completed/forecast partition, однородность ERA5-Land current/reference, минимум валидных reference-лет, обязательные показатели, тесты, Alembic и Bash. Пользовательские данные не изменяются.

В GitHub Actions также есть еженедельный и ручной workflow **Live provider smoke**. Его JSON-результаты сохраняются как artifact на 14 суток. Внешний provider workflow отделён от обычного PR CI, чтобы временная недоступность API не блокировала локально воспроизводимые изменения.

## 5. Telegram smoke для двух полей

1. Отправьте `/start`.
2. Откройте **«Мои поля»**.
3. Добавьте поле `Северное`, координаты, культуру и дату сезона.
4. Добавьте поле `Южное` с другими параметрами.
5. Задайте разные настройки уведомлений.
6. Переключайтесь между полями и проверяйте восстановление сезона, фазы и настроек.
7. Сформируйте отдельный агроотчёт для каждого поля.

Проверьте, что отчёт:

- показывает активное поле;
- разделяет реанализ, завершённое прошлое и прогноз;
- использует отдельный однородный ERA5-Land-период для сравнения 1991–2020;
- показывает фактическую последнюю дату ERA5-Land;
- не заявляет сезонную сумму при неполном покрытии;
- не выводит `0` вместо отсутствующих данных;
- не называет frost screening вероятностью повреждения;
- не называет эмпирический процентиль вероятностью, SPI/SPEI или станционной нормой.

## 6. Конфигурация

```text
/etc/crop-forecast-bot.env
```

Минимальный production-набор:

```dotenv
APP_ENV=production
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=postgresql+asyncpg://cropbot:...@127.0.0.1:5432/crop_forecast_bot
REDIS_URL=redis://127.0.0.1:6379/0
COORDINATION_NAMESPACE=crop-forecast-bot
SCHEDULER_TIMEZONE=Europe/Moscow
HEARTBEAT_FILE=/run/crop-forecast-bot/heartbeat
OPEN_METEO_CACHE_PATH=/var/cache/crop-forecast-bot/openmeteo
RAG_ENABLED=false
INSTALL_RAG_PROFILE=0
```

После изменения:

```bash
sudo systemctl restart crop-forecast-bot
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

## 7. Опциональный RAG

```dotenv
INSTALL_RAG_PROFILE=1
RAG_ENABLED=true
LLM_PROVIDER=groq
GROQ_API_KEY=...
```

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
sudo install -o cropbot -g cropbot -m 640 document.pdf \
  /var/lib/crop-forecast-bot/data/literature/document.pdf
sudo -u cropbot bash -lc '
  cd /opt/crop-forecast-bot/current &&
  .venv/bin/python -m src.knowledge.indexer --reset
'
```

## 8. Обновление и откат

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

Перед обновлением сохраняется PostgreSQL dump. Код и systemd-unit откатываются вместе при неуспешном healthcheck. Миграции БД автоматически назад не отменяются.

## 9. Проверка восстановления backup

Последний dump можно безопасно проверить без изменения production-БД:

```bash
sudo bash \
  /opt/crop-forecast-bot/current/scripts/verify-backup-restore.sh
```

Либо указать конкретный custom-format dump:

```bash
sudo bash \
  /opt/crop-forecast-bot/current/scripts/verify-backup-restore.sh \
  /var/backups/crop-forecast-bot/database-YYYYMMDDTHHMMSSZ.dump
```

Скрипт создаёт временную локальную БД, выполняет `pg_restore --exit-on-error`, сравнивает schema fingerprint, Alembic revision и точные fingerprints таблиц `users`, `fields`, `crop_seasons`, затем всегда удаляет verification database. Удалённые PostgreSQL-инстансы намеренно не поддерживаются этим root-runbook.

## 10. Диагностика

```bash
sudo systemctl status crop-forecast-bot --no-pager -l
sudo journalctl -u crop-forecast-bot -n 200 --no-pager
sudo systemctl status postgresql redis-server
redis-cli ping
```

При устаревшей схеме:

```bash
cd /opt/crop-forecast-bot/current
sudo -u cropbot .venv/bin/alembic current
sudo -u cropbot .venv/bin/alembic upgrade head
sudo systemctl restart crop-forecast-bot
```

Если сезонный реанализ или ERA5-Land недоступны, основной оперативный отчёт продолжает работу и явно показывает деградацию качества. Отсутствующие данные не подменяются прогнозом другой модели.
