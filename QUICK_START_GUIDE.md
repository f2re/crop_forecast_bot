# Быстрый старт и эксплуатация Crop Forecast Bot

Это руководство описывает нативную установку на Debian 12, Ubuntu Server и совместимых Astra Linux окружениях. Бот запускается отдельным непривилегированным пользователем через systemd; PostgreSQL и Redis работают как системные службы ОС.

## 1. Подготовка

Потребуются:

- root-доступ к серверу;
- исходящий HTTPS-доступ к GitHub, Telegram API и Open-Meteo;
- токен Telegram-бота от `@BotFather`;
- минимум 2 ГБ RAM для базового режима; RAG с локальными embeddings требует больше памяти и диска.

Создайте root-only файл с токеном:

```bash
sudo install -m 600 /dev/null /root/cropbot-token
sudo editor /root/cropbot-token
```

В файле должна быть одна строка с токеном без кавычек.

## 2. Первая установка

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

Скрипт автоматически:

1. устанавливает системные пакеты;
2. создаёт пользователя и группу `cropbot`;
3. запускает PostgreSQL и Redis;
4. создаёт отдельные роль и БД PostgreSQL со случайным паролем;
5. записывает `/etc/crop-forecast-bot.env` с правами `0640 root:cropbot`;
6. клонирует выбранную ветку в новый release-каталог;
7. создаёт virtualenv и устанавливает зависимости;
8. выполняет `pip check`, компиляцию модулей и runtime preflight;
9. устанавливает systemd units;
10. запускает бот и проверяет heartbeat.

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
- PostgreSQL check: без ошибок;
- Redis check: без ошибок.

Логи в реальном времени:

```bash
sudo journalctl -u crop-forecast-bot -f
```

Последние сто строк:

```bash
sudo journalctl -u crop-forecast-bot -n 100 --no-pager
```

## 4. Конфигурация

Production-конфигурация находится только здесь:

```text
/etc/crop-forecast-bot.env
```

Редактирование:

```bash
sudo editor /etc/crop-forecast-bot.env
sudo systemctl restart crop-forecast-bot
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

Минимальные параметры:

```dotenv
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=postgresql+asyncpg://cropbot:...@127.0.0.1:5432/crop_forecast_bot
REDIS_URL=redis://127.0.0.1:6379/0
HEARTBEAT_FILE=/run/crop-forecast-bot/heartbeat
OPEN_METEO_CACHE_PATH=/var/cache/crop-forecast-bot/openmeteo
```

Не публикуйте этот файл и не копируйте его в репозиторий.

## 5. Обновление

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
```

Перед переключением версии создаётся резервная копия PostgreSQL. Новая версия разворачивается отдельно от активной, поэтому неудачная установка зависимостей не повреждает работающий release.

После переключения скрипт проверяет systemd state и heartbeat. При ошибке он возвращает предыдущий release и перезапускает сервис.

Проверка результата:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

## 6. Ручной откат

Откат к предыдущей версии:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

Список сохранённых версий:

```bash
sudo find /opt/crop-forecast-bot/releases -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
```

Откат к конкретной версии:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh \
  /opt/crop-forecast-bot/releases/<release-directory>
```

Откат кода не отменяет миграции БД. Dump перед обновлением хранится в `/var/backups/crop-forecast-bot/`.

## 7. Автозапуск и самовосстановление

Основной unit:

```bash
systemctl status crop-forecast-bot
systemctl is-enabled crop-forecast-bot
```

systemd выполняет:

- запуск после сети, PostgreSQL и Redis;
- `ExecStartPre` диагностику;
- автоматический restart после аварии;
- readiness notification после запуска scheduler и polling;
- watchdog restart, если event loop перестал обновлять heartbeat;
- штатное завершение bot session, storage, scheduler и DB engine.

## 8. Автоматическое обновление

По умолчанию выключено. Включить еженедельный запуск `update.sh main`:

```bash
sudo systemctl enable --now crop-forecast-bot-update.timer
systemctl list-timers crop-forecast-bot-update.timer
```

Выключить:

```bash
sudo systemctl disable --now crop-forecast-bot-update.timer
```

Автоматическое обновление следует использовать только для защищённой ветки с обязательным зелёным CI.

## 9. Постоянные данные

```text
/var/lib/crop-forecast-bot/data/          данные приложения
/var/lib/crop-forecast-bot/data/literature/ документы RAG
/var/lib/crop-forecast-bot/models/        локальные модели и артефакты
/var/cache/crop-forecast-bot/             кэши
/var/backups/crop-forecast-bot/           PostgreSQL dumps
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

## 10. Типовые неисправности

### Сервис не запускается

```bash
sudo systemctl status crop-forecast-bot --no-pager -l
sudo journalctl -u crop-forecast-bot -n 200 --no-pager
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

### Ошибка PostgreSQL

```bash
sudo systemctl status postgresql
sudo -u postgres psql -c '\l'
```

Проверьте `DATABASE_URL` в `/etc/crop-forecast-bot.env`.

### Ошибка Redis

```bash
sudo systemctl status redis-server
redis-cli ping
```

Ожидаемый ответ: `PONG`.

### Heartbeat устарел

```bash
sudo systemctl restart crop-forecast-bot
sudo journalctl -u crop-forecast-bot -n 100 --no-pager
```

Если процесс снова зависает, сохраните журнал и не отключайте watchdog: нужно устранять блокирующий вызов в application/infrastructure слое.

### Обновление откатилось

```bash
sudo journalctl -u crop-forecast-bot-update -n 200 --no-pager
sudo ls -lh /var/backups/crop-forecast-bot/
```

Активная версия остаётся на предыдущем release. Исправьте причину в отдельной ветке и повторите обновление после зелёного CI.
