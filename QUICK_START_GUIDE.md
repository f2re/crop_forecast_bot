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

Read-only smoke реального Open-Meteo:

```bash
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh \
  --live-provider 55.75 37.62 2026-04-15
```

Команда проверяет структуру ответа, локальные даты, completed/forecast partition, тесты, Alembic и Bash. Пользовательские данные не изменяются.

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
- не заявляет сезонную сумму при неполном покрытии;
- не выводит `0` вместо отсутствующих данных;
- не называет frost screening вероятностью повреждения.

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

Перед обновлением сохраняется PostgreSQL dump. Код откатывается автоматически при неуспешном healthcheck, но миграции БД автоматически назад не отменяются.

## 9. Диагностика

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

Если сезонный реанализ недоступен, в журнале будет `Season history unavailable`; бот продолжит работу с коротким окном и явно пометит ограничение.
