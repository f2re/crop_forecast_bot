# 🌾 Crop Forecast Bot

Telegram-бот для оперативной агрометеорологической оценки:
**поле → культура → сезон → отчёт и предупреждения**.

**Production:** Python 3.11+, aiogram 3.x, PostgreSQL, Redis, Alembic и systemd. Docker не используется.

## ✅ Что работает

- 🗺 несколько полей в одном Telegram-профиле;
- ✅ выбор одного активного поля для отчётов и фоновых уведомлений;
- 📍 геолокация или ручной ввод координат;
- ✏️ создание, переименование, переключение и обновление координат поля;
- 🌱 отдельная культура и активный сезон каждого поля;
- 📅 дата посева/начала сезона и фактическая фаза по наблюдению пользователя;
- 🕒 сохранение timezone и высоты с указанием источника метаданных;
- 🌦 Open-Meteo Forecast API для оперативного прошлого и прогноза;
- 🗓 Open-Meteo Historical Weather API для сезонного реанализа;
- 🌿 ГДД с crop-specific `Tbase` и контролем покрытия/пропусков;
- 💧 ГТК только при достаточном числе валидных тёплых суток;
- 🚿 баланс осадки − ET₀ провайдера;
- 🌡 общий скрининг Tmin воздуха на высоте 2 м;
- 📨 отдельные настройки ежедневного отчёта и температурных алертов для каждого поля;
- 🔒 Redis FSM, distributed locks и дедупликация уведомлений;
- 🗃 Alembic-миграции PostgreSQL;
- ♻️ нативные Bash-скрипты установки, обновления, диагностики и отката.

> Бот не выдаёт короткий архив за климатическую норму, общий порог Tmin за порог повреждения культуры, эвристику за прогноз урожайности или синтетическую ML-модель за валидированную production-модель.

## 🧑‍🌾 Работа в Telegram

1. Откройте `/start`.
2. Выберите **«Мои поля»**.
3. Добавьте поле или сделайте существующее активным.
4. Выберите культуру активного поля.
5. Укажите дату посева/начала сезона и, при наличии, фактическую фазу.
6. Нажмите **«Агроотчёт»**.

### Управление полями

У каждого поля независимо сохраняются:

- название и координаты;
- timezone и высота модели;
- культура, дата сезона и фактическая фаза;
- ежедневный отчёт;
- температурные алерты.

В интерфейсе одно поле помечено `✅` как активное. Ручной отчёт, раздел сезона и scheduler используют именно его. Переключение поля восстанавливает его собственный сезон и настройки.

### Команды бота

| Команда | Назначение |
|---|---|
| `/start` | открыть главное меню и активное поле |
| `/help` | показать пользовательскую справку |
| `/cancel` | отменить текущий ввод и очистить FSM |

## 📊 Что содержит отчёт

Отчёт отвечает на четыре вопроса:

1. **Что происходит** — Tmin, влагообеспеченность, ГДД и водный баланс.
2. **Насколько надёжно** — источники, период, покрытие, пропуски и fallback.
3. **Что проверить сейчас** — локальный прогноз, фазу и микрорельеф.
4. **Когда обновить оценку** — после нового прогноза или изменения поля/фазы.

Источники не смешиваются:

- **реанализ** — прошлый сезонный ряд Historical Weather API;
- **оперативное прошлое модели** — короткое окно Forecast API;
- **прогноз** — будущие дни Forecast API.

Если реанализ недоступен или не покрывает дату сезона, бот показывает ГДД только **за доступный период**.

## 🚀 Установка на сервер

Поддерживается нативная установка на Debian, Ubuntu и совместимые Astra Linux окружения.

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo bash scripts/deploy.sh
```

Первый запуск установит системные пакеты, PostgreSQL и Redis, создаст пользователя `cropbot`, БД и защищённый файл:

```text
/etc/crop-forecast-bot.env
```

Задайте токен и повторите установку:

```bash
sudo editor /etc/crop-forecast-bot.env
sudo bash scripts/deploy.sh
```

Неинтерактивная установка:

```bash
sudo install -m 600 /dev/null /root/cropbot-token
sudo editor /root/cropbot-token
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

Deploy создаёт отдельный release и virtualenv, делает backup PostgreSQL, выполняет `alembic upgrade head`, preflight, атомарное переключение версии и проверку heartbeat.

## 🛠 Команды администратора

```bash
# Полная диагностика
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh

# Краткая справка
bash /opt/crop-forecast-bot/current/scripts/help.sh

# Логи
sudo journalctl -u crop-forecast-bot -f

# Перезапуск
sudo systemctl restart crop-forecast-bot

# Обновление
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main

# Откат
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

### Эксплуатационные скрипты

| Скрипт | Назначение |
|---|---|
| `scripts/deploy.sh` | установить ОС-зависимости, PostgreSQL, Redis и systemd-service |
| `scripts/update.sh` | создать backup/release, применить миграции и проверить запуск |
| `scripts/rollback.sh` | вернуть предыдущий или указанный release |
| `scripts/status.sh` | проверить service, commit, heartbeat, PostgreSQL, Redis и журнал |
| `scripts/help.sh` | вывести готовую шпаргалку |
| `scripts/install-systemd.sh` | совместимый alias нативной установки |

## 🔄 Обновление и откат

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
```

Обновление выполняет:

1. PostgreSQL dump;
2. отдельный release-каталог и virtualenv;
3. `pip check` и `compileall`;
4. `alembic upgrade head`;
5. runtime/schema preflight;
6. атомарное переключение `current`;
7. проверку systemd и heartbeat;
8. автоматический возврат предыдущего кода при ошибке.

Ручной откат:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

> Код откатывается автоматически, схема БД — нет. Перед update создаётся backup; миграции должны быть обратно совместимыми либо иметь проверенный recovery-план.

## 🤖 Автоматическое обновление

Таймер установлен, но по умолчанию выключен:

```bash
sudo systemctl enable --now crop-forecast-bot-update.timer
systemctl list-timers crop-forecast-bot-update.timer
```

В production включайте его только для защищённой ветки `main` с обязательным зелёным CI.

## ⚙️ Конфигурация

Production-файл: `/etc/crop-forecast-bot.env`.

| Переменная | Назначение |
|---|---|
| `APP_ENV` | `production` требует PostgreSQL и Redis |
| `TELEGRAM_BOT_TOKEN` | токен от BotFather |
| `DATABASE_URL` | async SQLAlchemy URL `postgresql+asyncpg://...` |
| `REDIS_URL` | FSM, scheduler locks и дедупликация |
| `COORDINATION_NAMESPACE` | префикс Redis-ключей |
| `SCHEDULER_TIMEZONE` | системная timezone scheduler |
| `HEARTBEAT_FILE` | heartbeat asyncio event loop |
| `OPEN_METEO_CACHE_PATH` | writable cache Open-Meteo |
| `CDS_API_URL`, `CDS_API_KEY` | опциональная ERA5/CDS-интеграция |
| `OPENROUTER_API_KEY` | опциональный LLM-провайдер |

После изменения:

```bash
sudo systemctl restart crop-forecast-bot
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

## 🗃 Миграции БД

Deploy/update применяют миграции автоматически. Ручные команды:

```bash
cd /opt/crop-forecast-bot/current
sudo -u cropbot .venv/bin/alembic current
sudo -u cropbot .venv/bin/alembic upgrade head
```

Схема:

- `users` — Telegram identity и временные compatibility-поля;
- `fields` — поле, координаты, timezone, высота, active flag и настройки уведомлений;
- `crop_seasons` — культура, дата сезона и фактическая фаза.

Миграции:

- `20260710_0001` — baseline `users`;
- `20260710_0002` — `fields` и `crop_seasons`, backfill legacy-профилей;
- `20260710_0003` — provenance timezone/elevation и field-level notifications.

Приложение не запускается при устаревшей Alembic-ревизии.

## 📂 Системные пути

| Путь | Назначение |
|---|---|
| `/opt/crop-forecast-bot/releases/` | изолированные версии приложения |
| `/opt/crop-forecast-bot/current` | активная версия |
| `/opt/crop-forecast-bot/previous` | предыдущая версия |
| `/etc/crop-forecast-bot.env` | секреты и runtime-настройки |
| `/var/lib/crop-forecast-bot/` | постоянные данные, литература и модели |
| `/var/cache/crop-forecast-bot/` | pip, embeddings и погодный cache |
| `/var/backups/crop-forecast-bot/` | PostgreSQL backups |

## 🧪 Разработка и проверки

Нужны PostgreSQL и Redis.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN, DATABASE_URL и REDIS_URL
alembic upgrade head
python -m src.bot.main
```

Перед commit:

```bash
ruff check alembic config src tests
python -m compileall -q alembic config src tests
bash -n scripts/*.sh
shellcheck -x scripts/deploy.sh scripts/update.sh scripts/rollback.sh \
  scripts/status.sh scripts/help.sh scripts/install-systemd.sh
python -m pytest -q
```

## 🏗 Архитектура

```text
Telegram handlers / persistent FSM
        ↓
application services + ports
        ↓
domain / agro calculations
        ↓
infrastructure adapters
  ├─ Open-Meteo forecast + historical reanalysis
  ├─ PostgreSQL / Alembic
  ├─ Redis coordination
  └─ RAG
```

Единственная точка запуска:

```bash
python -m src.bot.main
```

## 📐 Научные ограничения

- ГДД: `max(0, (Tmax + Tmin) / 2 − Tbase)`, единицы `°C·сут`.
- Сезонная сумма ГДД заявляется только при покрытии даты начала сезона.
- Таблицы фаз пока не являются валидированной региональной моделью; автоматическая фаза не выводится.
- Фактическая фаза — пользовательское наблюдение.
- ГТК требует тёплых суток `Tср > 10°C` и достаточного валидного периода.
- ET₀ поступает от провайдера; локальная FAO-56 Penman–Monteith пока не реализована.
- Frost screening использует Tmin воздуха 2 м и не моделирует температуру растений, микрорельеф, ensemble uncertainty или crop-specific damage threshold.
- Реанализ, оперативное прошлое и прогноз показываются раздельно.
- SPI по короткому прогнозу не рассчитывается.

## 🆘 Диагностика

```bash
# Состояние и ошибки
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
sudo journalctl -u crop-forecast-bot -n 200 --no-pager

# PostgreSQL и Redis
sudo systemctl status postgresql redis-server
redis-cli ping

# Конфигурация, schema и writable paths
cd /opt/crop-forecast-bot/current
sudo -u cropbot .venv/bin/python -m src.ops.doctor --runtime
```

Ожидаемый ответ Redis: `PONG`. Doctor должен подтвердить runtime dependencies и актуальную Alembic-схему.

## 📚 Документация

- [Быстрый старт и эксплуатация](QUICK_START_GUIDE.md)
- [Аудит проекта](docs/AUDIT_2026-07-10.md)
- [План модернизации](docs/DEVELOPMENT_PLAN.md)
- [Настройка RAG](RAG_GUIDE.md)

## 🗺 Следующие задачи

- интеграционные тесты с реальными PostgreSQL/Redis и restart FSM;
- clean-host smoke test deploy/update/rollback на Debian/Astra;
- удаление legacy-полей `users.latitude/longitude/selected_crop/daily_digest` после production verification;
- валидация GDD-фаз по культурам и регионам;
- сезонный источник для корректного ГТК с контролем пропусков;
- provider adapters для ERA5, SoilGrids и спутниковых данных;
- dependency lock, structured logging, метрики и аудит fallback-режимов.
