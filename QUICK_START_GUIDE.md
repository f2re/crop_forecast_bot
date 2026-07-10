# 🚀 Быстрый старт и эксплуатация

Нативная установка для Debian 12, Ubuntu Server и совместимых Astra Linux окружений. Бот работает от непривилегированного пользователя через systemd; PostgreSQL и Redis запускаются как службы ОС.

## 1. Подготовка

Нужны:

- root-доступ;
- исходящий HTTPS к GitHub, Telegram API и Open-Meteo;
- токен от `@BotFather`;
- минимум 2 ГБ RAM для базового режима.

Создайте root-only файл токена:

```bash
sudo install -m 600 /dev/null /root/cropbot-token
sudo editor /root/cropbot-token
```

Файл должен содержать одну строку с токеном без кавычек.

## 2. Первая установка

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

Скрипт:

1. установит системные пакеты;
2. создаст пользователя `cropbot`;
3. запустит PostgreSQL и Redis;
4. создаст роль и БД PostgreSQL;
5. запишет `/etc/crop-forecast-bot.env`;
6. создаст release и virtualenv;
7. сделает backup БД;
8. выполнит `alembic upgrade head`;
9. запустит runtime preflight;
10. установит systemd units и проверит heartbeat.

Другая ветка:

```bash
sudo BRANCH=my-branch TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

## 3. Проверка сервера

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

Ожидается:

```text
service: active
heartbeat: healthy
PostgreSQL: available
Redis: available
schema: current
```

Логи:

```bash
sudo journalctl -u crop-forecast-bot -f
sudo journalctl -u crop-forecast-bot -n 100 --no-pager
```

## 4. Smoke test в Telegram

1. Отправьте `/start`.
2. Откройте **«Мои поля»**.
3. Добавьте поле `Северное` и передайте координаты.
4. Выберите культуру и укажите дату сезона.
5. Включите ежедневный отчёт, отключите температурные алерты.
6. Добавьте поле `Южное` с другими координатами.
7. Выберите другую культуру/дату и противоположные настройки уведомлений.
8. Переключитесь между полями.

Проверьте, что для каждого поля независимо восстанавливаются:

- координаты;
- культура;
- дата сезона и фаза;
- timezone/высота после отчёта;
- настройки ежедневного отчёта и температурных алертов.

Сформируйте **«Агроотчёт»** для каждого поля. В сообщении должны быть название активного поля, источник данных, период и ограничения.

## 5. Конфигурация

Production-файл:

```text
/etc/crop-forecast-bot.env
```

Редактирование и применение:

```bash
sudo editor /etc/crop-forecast-bot.env
sudo systemctl restart crop-forecast-bot
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

Минимум:

```dotenv
APP_ENV=production
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=postgresql+asyncpg://cropbot:...@127.0.0.1:5432/crop_forecast_bot
REDIS_URL=redis://127.0.0.1:6379/0
HEARTBEAT_FILE=/run/crop-forecast-bot/heartbeat
OPEN_METEO_CACHE_PATH=/var/cache/crop-forecast-bot/openmeteo
```

Не публикуйте этот файл и не копируйте его в репозиторий.

## 6. Миграции

```bash
cd /opt/crop-forecast-bot/current
sudo -u cropbot .venv/bin/alembic current
sudo -u cropbot .venv/bin/alembic heads
```

Ожидаемая head-revision текущего среза:

```text
20260710_0003
```

Принудительное обновление:

```bash
sudo -u cropbot .venv/bin/alembic upgrade head
```

Миграция `0003` переносит legacy-настройку ежедневного отчёта в активное поле и добавляет отдельный переключатель температурных алертов. Для существующей timezone/высоты сохраняется пометка, что точный прежний provider не был записан.

## 7. Обновление

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
```

Update создаёт PostgreSQL dump, новый release и virtualenv, применяет миграции, выполняет preflight и только затем переключает `current`. При неуспешном запуске восстанавливается предыдущий код.

Проверка:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

## 8. Откат

К предыдущему release:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

Список версий:

```bash
sudo find /opt/crop-forecast-bot/releases \
  -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
```

К выбранной версии:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh \
  /opt/crop-forecast-bot/releases/<release-directory>
```

Откат кода не отменяет миграции БД. Dumps находятся в `/var/backups/crop-forecast-bot/`.

## 9. Автозапуск и обновление

```bash
systemctl status crop-forecast-bot
systemctl is-enabled crop-forecast-bot
```

Включить еженедельный update timer:

```bash
sudo systemctl enable --now crop-forecast-bot-update.timer
systemctl list-timers crop-forecast-bot-update.timer
```

Выключить:

```bash
sudo systemctl disable --now crop-forecast-bot-update.timer
```

Используйте автоматическое обновление только для защищённой ветки с обязательным зелёным CI.

## 10. Постоянные данные

```text
/var/lib/crop-forecast-bot/data/             данные приложения
/var/lib/crop-forecast-bot/data/literature/  документы RAG
/var/lib/crop-forecast-bot/models/           локальные модели
/var/cache/crop-forecast-bot/                caches
/var/backups/crop-forecast-bot/              PostgreSQL dumps
```

## 11. Типовые неисправности

### Бот не запускается

```bash
sudo systemctl status crop-forecast-bot --no-pager -l
sudo journalctl -u crop-forecast-bot -n 200 --no-pager
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

### PostgreSQL

```bash
sudo systemctl status postgresql
sudo -u postgres psql -c '\l'
```

Проверьте `DATABASE_URL`.

### Redis

```bash
sudo systemctl status redis-server
redis-cli ping
```

Ожидается `PONG`.

### Устаревшая schema

```bash
cd /opt/crop-forecast-bot/current
sudo -u cropbot .venv/bin/alembic current
sudo -u cropbot .venv/bin/alembic upgrade head
sudo systemctl restart crop-forecast-bot
```

### Update откатился

```bash
sudo journalctl -u crop-forecast-bot-update -n 200 --no-pager
sudo ls -lh /var/backups/crop-forecast-bot/
```

Исправьте причину в отдельной ветке, дождитесь зелёного CI и повторите update.
