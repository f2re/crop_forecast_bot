# 🚀 Быстрый старт и эксплуатация Crop Forecast Bot

Нативная установка для Debian 12, Ubuntu Server и совместимых Astra Linux окружений. Бот работает от отдельного пользователя через systemd; PostgreSQL и Redis запускаются системными службами ОС.

## 1. Подготовка

Потребуются:

- root-доступ;
- исходящий HTTPS к GitHub, Telegram API и Open-Meteo;
- токен Telegram-бота от `@BotFather`;
- минимум 2 ГБ RAM для базового режима;
- больше памяти и диска при использовании локальных RAG embeddings.

Создайте root-only файл с токеном:

```bash
sudo install -m 600 /dev/null /root/cropbot-token
sudo editor /root/cropbot-token
```

В файле должна быть одна строка токена без кавычек.

## 2. Первая установка

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

Скрипт:

1. устанавливает Python и системные библиотеки;
2. создаёт пользователя и группу `cropbot`;
3. запускает PostgreSQL и Redis;
4. создаёт отдельные роль и БД со случайным паролем;
5. записывает `/etc/crop-forecast-bot.env` с правами `0640 root:cropbot`;
6. создаёт новый release и virtualenv;
7. выполняет PostgreSQL backup;
8. применяет `alembic upgrade head`;
9. выполняет `pip check`, `compileall` и runtime preflight;
10. устанавливает systemd units;
11. запускает сервис и проверяет heartbeat.

Для установки другой ветки:

```bash
sudo BRANCH=my-branch TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

## 3. Проверка после установки

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

Ожидается:

- service state: `active`;
- heartbeat: `healthy`;
- PostgreSQL и Alembic schema: без ошибок;
- Redis check: без ошибок.

Логи:

```bash
sudo journalctl -u crop-forecast-bot -f
sudo journalctl -u crop-forecast-bot -n 100 --no-pager
```

## 4. Проверка Telegram-сценария

1. Отправьте `/start`.
2. Откройте **«Моё поле»** и передайте координаты.
3. Выберите культуру.
4. Откройте **«Сезон и фаза»**.
5. Введите дату посева, например `15.04.2026`.
6. При наличии наблюдения выберите фактическую фазу.
7. Откройте **«Агроотчёт»**.

Проверьте, что отчёт показывает:

- имя поля, координаты, timezone и высоту модели;
- культуру, дату сезона и ручную фазу;
- ГДД с начала сезона либо явную пометку неполного покрытия;
- отдельные подписи реанализа и прогноза;
- ограничения frost screening и источники данных.

## 5. Конфигурация

Production-конфигурация:

```text
/etc/crop-forecast-bot.env
```

Редактирование и проверка:

```bash
sudo editor /etc/crop-forecast-bot.env
sudo systemctl restart crop-forecast-bot
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

Минимальные параметры:

```dotenv
APP_ENV=production
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=postgresql+asyncpg://cropbot:...@127.0.0.1:5432/crop_forecast_bot
REDIS_URL=redis://127.0.0.1:6379/0
COORDINATION_NAMESPACE=crop-forecast-bot
HEARTBEAT_FILE=/run/crop-forecast-bot/heartbeat
OPEN_METEO_CACHE_PATH=/var/cache/crop-forecast-bot/openmeteo
```

Не публикуйте этот файл и не копируйте его в репозиторий.

## 6. Миграции БД

Текущая схема содержит:

- `users` — Telegram-профиль и настройки;
- `fields` — координаты, timezone, высота и active flag;
- `crop_seasons` — культура, дата сезона и фактическая фаза.

Ручная проверка:

```bash
cd /opt/crop-forecast-bot/current
sudo -u cropbot .venv/bin/alembic current
sudo -u cropbot .venv/bin/alembic heads
sudo -u cropbot .venv/bin/alembic upgrade head
```

Migration `20260710_0002` переносит legacy-координаты и культуру в `Основное поле` и активный сезон. Перед update/deploy создаётся PostgreSQL dump.

## 7. Обновление

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
```

Новая версия строится отдельно от активной. До переключения выполняются backup, миграции и preflight. После переключения проверяются systemd state и heartbeat. При ошибке код возвращается к предыдущему release.

Проверка результата:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

## 8. Ручной откат

К предыдущей версии:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

Список release-каталогов:

```bash
sudo find /opt/crop-forecast-bot/releases \
  -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
```

К конкретной версии:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh \
  /opt/crop-forecast-bot/releases/<release-directory>
```

Откат кода не отменяет миграции БД. Dumps находятся в `/var/backups/crop-forecast-bot/`.

## 9. Автозапуск и watchdog

```bash
systemctl status crop-forecast-bot
systemctl is-enabled crop-forecast-bot
```

systemd выполняет:

- запуск после сети, PostgreSQL и Redis;
- `ExecStartPre` проверку конфигурации и схемы;
- readiness notification после запуска scheduler и polling;
- автоматический restart после аварии;
- watchdog restart, если asyncio event loop не обновляет heartbeat;
- штатное закрытие bot session, FSM storage, scheduler и DB engine.

## 10. Автоматическое обновление

По умолчанию выключено.

Включить:

```bash
sudo systemctl enable --now crop-forecast-bot-update.timer
systemctl list-timers crop-forecast-bot-update.timer
```

Выключить:

```bash
sudo systemctl disable --now crop-forecast-bot-update.timer
```

Используйте автоматическое обновление только для защищённой ветки с обязательным зелёным CI.

## 11. Постоянные данные

```text
/var/lib/crop-forecast-bot/data/             данные приложения
/var/lib/crop-forecast-bot/data/literature/  документы RAG
/var/lib/crop-forecast-bot/models/           локальные артефакты
/var/cache/crop-forecast-bot/                погодный, pip и embedding cache
/var/backups/crop-forecast-bot/              PostgreSQL dumps
```

Добавление литературы:

```bash
sudo install -o cropbot -g cropbot -m 640 document.pdf \
  /var/lib/crop-forecast-bot/data/literature/document.pdf
sudo -u cropbot -H bash -lc '
  cd /opt/crop-forecast-bot/current &&
  .venv/bin/python -m src.knowledge.indexer
'
```

## 12. Типовые неисправности

### Сервис не запускается

```bash
sudo systemctl status crop-forecast-bot --no-pager -l
sudo journalctl -u crop-forecast-bot -n 200 --no-pager
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

### Alembic revision устарела

```bash
cd /opt/crop-forecast-bot/current
sudo -u cropbot .venv/bin/alembic current
sudo -u cropbot .venv/bin/alembic upgrade head
sudo systemctl restart crop-forecast-bot
```

### PostgreSQL недоступен

```bash
sudo systemctl status postgresql
sudo -u postgres psql -c '\l'
```

Проверьте `DATABASE_URL` в `/etc/crop-forecast-bot.env`.

### Redis недоступен

```bash
sudo systemctl status redis-server
redis-cli ping
```

Ожидаемый ответ: `PONG`.

### Сезонный ряд не загрузился

Проверьте журнал на сообщения `Season history unavailable`. Бот продолжит работу с коротким оперативным окном и пометит ГДД как сумму за доступный период. Не удаляйте эту пометку из пользовательского отчёта.

### Heartbeat устарел

```bash
sudo systemctl restart crop-forecast-bot
sudo journalctl -u crop-forecast-bot -n 100 --no-pager
```

Если процесс снова зависает, сохраняйте журнал и устраняйте блокирующий вызов в application/infrastructure слое. Watchdog отключать не следует.

### Обновление откатилось

```bash
sudo journalctl -u crop-forecast-bot-update -n 200 --no-pager
sudo ls -lh /var/backups/crop-forecast-bot/
```

Активной останется предыдущая версия. Исправьте причину в отдельной ветке и повторите update после зелёного CI.
