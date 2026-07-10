# 🌾 Crop Forecast Bot

Telegram-бот для оперативной агрометеорологической оценки поля: координаты → культура → понятный отчёт и предупреждения.

**Production-стек:** Python 3.11+, aiogram 3.x, PostgreSQL, Redis, Alembic и systemd. Контейнеры не используются.

## ✅ Что уже работает

- 📍 ввод поля геолокацией или координатами;
- 🌱 выбор культуры и сохранение профиля;
- 🌦 оперативный отчёт Open-Meteo;
- 🌡 скрининг риска заморозка по Tmin воздуха;
- 💧 ГТК при достаточном валидном периоде;
- 🌿 ГДД за доступное временное окно;
- 🚿 баланс осадки − ET₀;
- 🔔 ежедневные отчёты и фоновые проверки;
- 🧠 RAG-советник при наличии проиндексированной литературы;
- 🔒 Redis FSM, распределённые блокировки scheduler и дедупликация уведомлений;
- 🗃 версионирование схемы PostgreSQL через Alembic;
- ♻️ нативные установка, обновление, диагностика и откат через Bash + systemd.

> Бот не выдаёт короткий архив за климатическую норму, эвристику за прогноз урожайности или синтетическую ML-модель за научно валидированную модель.

## 🧑‍🌾 Как пользоваться в Telegram

1. Откройте `/start`.
2. Выберите **«Моё поле»** и отправьте геолокацию либо координаты.
3. Выберите культуру.
4. Нажмите **«Агропрогноз»**.

### Команды бота

| Команда | Назначение |
|---|---|
| `/start` | открыть главное меню |
| `/help` | показать короткую справку |
| `/cancel` | отменить текущий ввод |

## 🚀 Установка на сервер

Поддерживается нативная установка на Debian, Ubuntu и Astra Linux с совместимой пакетной базой.

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo bash scripts/deploy.sh
```

Первый запуск установит системные зависимости, PostgreSQL и Redis, создаст пользователя `cropbot`, БД и защищённый конфигурационный файл:

```text
/etc/crop-forecast-bot.env
```

Задайте Telegram-токен и повторите установку:

```bash
sudo editor /etc/crop-forecast-bot.env
sudo bash scripts/deploy.sh
```

Неинтерактивный вариант с root-only файлом токена:

```bash
sudo install -m 600 /dev/null /root/cropbot-token
sudo editor /root/cropbot-token
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

Скрипт создаёт отдельный release и virtualenv, выполняет резервное копирование, `alembic upgrade head`, preflight, атомарное переключение версии и проверку systemd heartbeat.

## 🛠 Шпаргалка администратора

```bash
# Полная диагностика
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh

# Краткая справка по командам
bash /opt/crop-forecast-bot/current/scripts/help.sh

# Логи в реальном времени
sudo journalctl -u crop-forecast-bot -f

# Перезапуск
sudo systemctl restart crop-forecast-bot

# Обновление из main
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main

# Откат к предыдущей версии
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

### Эксплуатационные скрипты

| Скрипт | Что делает |
|---|---|
| `scripts/deploy.sh` | устанавливает зависимости, БД, Redis и systemd-сервис |
| `scripts/update.sh` | создаёт backup и новый release, применяет миграции, проверяет запуск |
| `scripts/rollback.sh` | возвращает предыдущий или указанный release |
| `scripts/status.sh` | проверяет сервис, commit, heartbeat, PostgreSQL, Redis и журнал |
| `scripts/help.sh` | печатает готовую шпаргалку команд |
| `scripts/install-systemd.sh` | совместимый алиас нативной установки |

## 🔄 Обновление и откат

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
```

Обновление выполняется безопасным вертикальным срезом:

1. создаётся PostgreSQL dump;
2. код клонируется в новый release-каталог;
3. создаётся отдельный virtualenv;
4. выполняются `pip check` и `compileall`;
5. применяются Alembic-миграции;
6. проверяются схема БД, Redis и writable paths;
7. ссылка `current` переключается атомарно;
8. проверяются systemd state и heartbeat;
9. при ошибке возвращается предыдущий код.

Ручной откат:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

> Миграции БД автоматически назад не откатываются. Перед обновлением создаётся backup; изменения схемы должны быть обратно совместимыми либо иметь отдельный проверенный план восстановления.

## 🤖 Автоматическое обновление

Таймер устанавливается, но по умолчанию выключен:

```bash
sudo systemctl enable --now crop-forecast-bot-update.timer
systemctl list-timers crop-forecast-bot-update.timer
```

В production включайте его только при защищённой ветке `main` и обязательном зелёном CI.

## ⚙️ Конфигурация

Production-конфигурация: `/etc/crop-forecast-bot.env`.

| Переменная | Назначение |
|---|---|
| `APP_ENV` | `production` требует PostgreSQL и Redis |
| `TELEGRAM_BOT_TOKEN` | обязательный токен от BotFather |
| `DATABASE_URL` | async SQLAlchemy URL `postgresql+asyncpg://...` |
| `REDIS_URL` | FSM, scheduler locks и дедупликация уведомлений |
| `COORDINATION_NAMESPACE` | префикс Redis-ключей приложения |
| `SCHEDULER_TIMEZONE` | локальная зона фоновых задач |
| `HEARTBEAT_FILE` | heartbeat asyncio event loop |
| `OPEN_METEO_CACHE_PATH` | writable кэш Open-Meteo |
| `CDS_API_URL`, `CDS_API_KEY` | опциональная интеграция ERA5/CDS |
| `OPENROUTER_API_KEY` | опциональный LLM-провайдер |

После изменения конфигурации:

```bash
sudo systemctl restart crop-forecast-bot
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

## 🗃 Миграции базы данных

Миграции автоматически выполняются при deploy/update. Ручные команды:

```bash
cd /opt/crop-forecast-bot/current
sudo -u cropbot .venv/bin/alembic current
sudo -u cropbot .venv/bin/alembic upgrade head
```

Приложение не запускается при отсутствующей или устаревшей Alembic-ревизии.

## 📂 Системные пути

| Путь | Назначение |
|---|---|
| `/opt/crop-forecast-bot/releases/` | изолированные версии приложения |
| `/opt/crop-forecast-bot/current` | активная версия |
| `/opt/crop-forecast-bot/previous` | предыдущая версия |
| `/etc/crop-forecast-bot.env` | секреты и runtime-настройки |
| `/var/lib/crop-forecast-bot/` | постоянные данные, литература и модели |
| `/var/cache/crop-forecast-bot/` | pip, embeddings и погодный кэш |
| `/var/backups/crop-forecast-bot/` | резервные копии PostgreSQL |

## 🧪 Локальная разработка

Нужны доступные PostgreSQL и Redis.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN, DATABASE_URL и REDIS_URL
alembic upgrade head
python -m src.bot.main
```

Проверки перед commit:

```bash
ruff check alembic config src tests
bash -n scripts/*.sh
shellcheck -x scripts/deploy.sh scripts/update.sh scripts/rollback.sh \
  scripts/status.sh scripts/help.sh scripts/install-systemd.sh
python -m pytest -q
```

## 🏗 Архитектура

```text
Telegram handlers / FSM
        ↓
application services
        ↓
domain / agro calculations
        ↓
infrastructure: Open-Meteo · PostgreSQL · Redis · RAG
```

Единственная точка запуска:

```bash
python -m src.bot.main
```

## 📊 Научные ограничения

- Open-Meteo используется для оперативного окна: 14 суток назад и 7 суток вперёд.
- ГДД без даты посева показываются только за доступный период; фенофаза не выводится.
- ГТК не рассчитывается при недостаточном числе валидных тёплых суток.
- ET₀ обозначается как переменная провайдера.
- Риск заморозка — screening по Tmin воздуха на высоте 2 м; микрорельеф, температура поверхности и фактическая фаза культуры пока не моделируются.
- SPI по короткому прогнозу не рассчитывается.

## 🆘 Если бот не запускается

```bash
# 1. Состояние и последние ошибки
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh

# 2. Журнал
sudo journalctl -u crop-forecast-bot -n 200 --no-pager

# 3. PostgreSQL и Redis
sudo systemctl status postgresql redis-server
redis-cli ping

# 4. Конфигурация, схема и writable paths
cd /opt/crop-forecast-bot/current
sudo -u cropbot .venv/bin/python -m src.ops.doctor --runtime
```

Ожидаемый Redis-ответ: `PONG`. Doctor должен завершиться сообщением, что runtime dependencies и схема БД готовы.

## 📚 Документация

- [Быстрый старт и эксплуатация](QUICK_START_GUIDE.md)
- [Аудит проекта](docs/AUDIT_2026-07-10.md)
- [План модернизации](docs/DEVELOPMENT_PLAN.md)
- [Настройка RAG](RAG_GUIDE.md)

## 🗺 Ближайшие задачи

- модель поля: дата посева, сезон, фаза и timezone;
- интеграционные тесты PostgreSQL/Redis/API и restart FSM;
- provider interfaces для ERA5, SoilGrids и спутниковых источников;
- валидный сезонный ряд для ГТК;
- lock-файл зависимостей и clean-host smoke test Debian/Astra;
- structured logging, метрики и аудит fallback-режимов.
