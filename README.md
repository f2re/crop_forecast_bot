# 🌾 Crop Forecast Bot

Telegram-бот для оперативной агрометеорологической оценки поля:
**поле → культура → сезон → отчёт и предупреждения**.

**Production-стек:** Python 3.11+, aiogram 3.x, PostgreSQL, Redis, Alembic и systemd. Контейнеры не используются.

## ✅ Что работает

- 📍 поле задаётся геолокацией или координатами;
- 🌱 сохраняются культура, дата посева/начала сезона и фактическая фаза;
- 🕒 часовой пояс и высота модели сохраняются для поля после запроса погоды;
- 🌦 оперативный прогноз поступает из Open-Meteo Forecast API;
- 🗓 при заданной дате сезона ряд расширяется историческим реанализом Open-Meteo;
- 🌿 ГДД рассчитываются с crop-specific `Tbase` из единого каталога культур;
- 💧 ГТК выводится только при достаточном числе валидных тёплых суток;
- 🚿 рассчитывается баланс осадки − ET₀ провайдера;
- 🌡 выполняется общий скрининг риска по Tmin воздуха на высоте 2 м;
- 🔔 ежедневные отчёты и проверки заморозков защищены Redis-блокировками и дедупликацией;
- 🧠 RAG-советник отвечает только при наличии проиндексированных источников;
- 🗃 схема PostgreSQL управляется Alembic;
- ♻️ установка, обновление, диагностика и откат выполняются Bash-скриптами и systemd.

> Бот не выдаёт короткий архив за климатическую норму, общие пороги Tmin за пороги повреждения культуры, эвристику за прогноз урожайности или синтетическую ML-модель за валидированную production-модель.

## 🧑‍🌾 Работа в Telegram

1. Откройте `/start`.
2. Выберите **«Моё поле»** и передайте геолокацию либо координаты.
3. Выберите культуру.
4. Откройте **«Сезон и фаза»** и укажите дату посева/начала активного сезона.
5. При наличии полевого наблюдения выберите фактическую фазу.
6. Нажмите **«Агроотчёт»**.

Дата сезона нужна для накопления ГДД. Фаза сохраняется как **наблюдение пользователя**. Бот не угадывает её автоматически по непроверенным порогам.

### Команды бота

| Команда | Назначение |
|---|---|
| `/start` | открыть главное меню и профиль поля |
| `/help` | показать пользовательскую справку |
| `/cancel` | отменить текущий ввод и очистить FSM |

## 📊 Что содержит отчёт

Отчёт отвечает на четыре вопроса:

1. **Что происходит** — Tmin, влагообеспеченность, ГДД и водный баланс.
2. **Насколько надёжно** — источники, период покрытия, пропуски и fallback.
3. **Что проверить сейчас** — локальный прогноз, фазу и микрорельеф.
4. **Когда обновить оценку** — после нового прогноза или изменения состояния поля.

Источники разделены:

- **реанализ** — прошлый сезонный ряд из Historical Weather API;
- **оперативное прошлое модели** — короткое окно Forecast API;
- **прогноз** — будущие дни Forecast API.

При недоступности сезонного ряда бот не подменяет его коротким архивом: ГДД маркируются как сумма **за доступный период**.

## 🚀 Установка на сервер

Поддерживается нативная установка на Debian, Ubuntu и Astra Linux с совместимой пакетной базой.

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo bash scripts/deploy.sh
```

Первый запуск устанавливает системные зависимости, PostgreSQL и Redis, создаёт пользователя `cropbot`, БД и защищённый конфигурационный файл:

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

Deploy создаёт отдельный release и virtualenv, выполняет backup PostgreSQL, `alembic upgrade head`, preflight, атомарное переключение версии и проверку systemd heartbeat.

## 🛠 Шпаргалка администратора

```bash
# Полная диагностика
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh

# Справка по эксплуатационным командам
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

| Скрипт | Назначение |
|---|---|
| `scripts/deploy.sh` | установить зависимости, PostgreSQL, Redis и systemd-сервис |
| `scripts/update.sh` | создать backup и новый release, применить миграции, проверить запуск |
| `scripts/rollback.sh` | вернуть предыдущий либо указанный release |
| `scripts/status.sh` | проверить service, commit, heartbeat, PostgreSQL, Redis и журнал |
| `scripts/help.sh` | вывести готовую шпаргалку команд |
| `scripts/install-systemd.sh` | совместимый алиас нативной установки |

## 🔄 Обновление и откат

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
```

Порядок обновления:

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

> Миграции БД автоматически назад не откатываются. Перед обновлением создаётся backup; изменения схемы должны быть обратно совместимыми либо иметь проверенный план восстановления.

## 🤖 Автоматическое обновление

Таймер устанавливается, но по умолчанию выключен:

```bash
sudo systemctl enable --now crop-forecast-bot-update.timer
systemctl list-timers crop-forecast-bot-update.timer
```

В production включайте его только для защищённой ветки `main` с обязательным зелёным CI.

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

## 🗃 Миграции БД

Миграции автоматически выполняются при deploy/update. Ручные команды:

```bash
cd /opt/crop-forecast-bot/current
sudo -u cropbot .venv/bin/alembic current
sudo -u cropbot .venv/bin/alembic upgrade head
```

Актуальная схема разделяет:

- `users` — Telegram-профиль и настройки уведомлений;
- `fields` — координаты, timezone, высота и активность поля;
- `crop_seasons` — культура, дата посева/начала сезона и фактическая фаза.

Legacy-координаты пользователей переносятся в `Основное поле` миграцией `20260710_0002`. Приложение не запускается при устаревшей Alembic-ревизии.

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

- ГДД: `max(0, (Tmax + Tmin) / 2 − Tbase)`, единицы `°C·сут`; `Tbase` берётся из каталога культуры.
- Сезонная сумма ГДД заявляется только при покрытии заданной даты начала сезона.
- Пороговые таблицы фаз в каталоге пока не являются валидированной региональной моделью; автоматическая фаза не выводится.
- Фактическая фаза — пользовательское наблюдение, а не результат алгоритма.
- ГТК рассчитывается только по тёплым суткам `Tср > 10°C` и при достаточном числе валидных дней.
- ET₀ поступает от провайдера; локальная FAO-56 Penman–Monteith пока не реализована.
- Скрининг заморозка использует Tmin воздуха 2 м. Он не моделирует температуру поверхности растений, микрорельеф и crop-specific повреждение.
- Реанализ, оперативное прошлое модели и прогноз показываются как разные типы данных.
- SPI по короткому прогнозу не рассчитывается.

## 🆘 Диагностика

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

Ожидаемый Redis-ответ: `PONG`. Doctor должен подтвердить готовность runtime dependencies и Alembic-схемы.

## 📚 Документация

- [Быстрый старт и эксплуатация](QUICK_START_GUIDE.md)
- [Аудит проекта](docs/AUDIT_2026-07-10.md)
- [План модернизации](docs/DEVELOPMENT_PLAN.md)
- [Настройка RAG](RAG_GUIDE.md)

## 🗺 Следующие задачи

- поддержка нескольких полей и переключение активного поля;
- интеграционные тесты PostgreSQL/Redis/API и restart FSM;
- валидация GDD-фаз по культурам и регионам;
- сезонный источник для научно корректного ГТК с контролем пропусков;
- provider interfaces для ERA5, SoilGrids и спутниковых данных;
- lock-файл зависимостей и clean-host smoke test Debian/Astra;
- structured logging, метрики и аудит fallback-режимов.
