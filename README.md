# 🌾 Crop Forecast Bot

Telegram-бот для оперативной агрометеорологической оценки полей:
**поле → культура → сезон → проверяемый отчёт → уведомления**.

[![CI](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml/badge.svg)](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml)

**Production:** Python 3.11+, aiogram 3.x, PostgreSQL, Redis, Alembic и systemd. Docker не используется.

## ✅ Что работает

- 🗺 несколько полей в одном Telegram-профиле;
- 📍 геолокация и ручной ввод координат;
- ✏️ создание, переименование, переключение и изменение координат;
- 🌱 отдельные культура, дата посева и фактическая фаза каждого поля;
- 🌦 оперативный прогноз Open-Meteo;
- 🗓 сезонный реанализ Open-Meteo Historical Weather API;
- 🌿 ГДД с crop-specific `Tbase`, контролем покрытия и пропусков;
- 💧 ГТК Селянинова только для валидного завершённого тёплого окна;
- 🚿 разность осадки − ET₀ без фиктивных нулей;
- 🌡 скрининг прогнозной Tmin воздуха на высоте 2 м;
- 📨 отдельные ежедневные отчёты и температурные алерты для активного поля;
- 🔒 Redis FSM, распределённые leases и дедупликация;
- 🗃 обязательные Alembic-миграции;
- ♻️ Bash-установка, обновление, диагностика и откат через systemd;
- 📚 опциональная RAG-база знаний с отображением источников.

> Отсутствующие данные не заменяются эвристикой. Показатель не рассчитывается либо явно помечается как ограниченный.

## ⛔ Что не заявляется

В production пока нет:

- прогноза урожайности или валидированной ML-модели;
- SPI по короткому прогнозу;
- локального FAO-56 Penman–Monteith;
- production-интеграции SoilGrids, Sentinel-2, MODIS или ERA5-Land;
- crop/phase-specific вероятности повреждения заморозком;
- автоматической фенофазы по непроверенным GDD-порогам;
- доз удобрений и препаратов без нормативного источника.

Полная матрица: [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md).

## 🧑‍🌾 Работа в Telegram

1. Отправьте `/start`.
2. Откройте **«Мои поля»**.
3. Добавьте поле или сделайте существующее активным.
4. Выберите культуру.
5. Укажите дату посева/начала сезона.
6. При наличии наблюдения выберите фактическую фазу.
7. Нажмите **«Агроотчёт»**.

У каждого поля независимо сохраняются координаты, культура, сезон, фаза и настройки уведомлений. Ручной отчёт и scheduler используют активное поле.

### Команды

| Команда | Назначение |
|---|---|
| `/start` | главное меню и активное поле |
| `/help` | пользовательская справка |
| `/cancel` | отмена ввода и очистка FSM |

## 📊 Структура отчёта

Отчёт отвечает на четыре вопроса:

1. **Что происходит** — температурный риск, ГДД и влагообеспеченность.
2. **Насколько надёжно** — источник, период, покрытие и пропуски.
3. **Что проверить сейчас** — локальный прогноз, фазу и микрорельеф.
4. **Когда обновить оценку** — после нового прогноза или изменения состояния поля.

Типы данных разделены:

- `reanalysis` — прошлый ряд Historical Weather API;
- `operational_past` — завершённые прошлые локальные сутки Forecast API;
- `forecast` — текущие и будущие локальные сутки.

Текущий локальный день не считается завершённым прошлым периодом.

## 📐 Расчёты

### ГДД

```text
GDDday = max(0, min(Tmean, Tupper) − Tbase)
```

- единицы: `°C·сут`;
- `Tbase` берётся из единого каталога культур;
- `Tupper` применяется только при явной настройке;
- прошлый период и прогнозный прирост считаются отдельно;
- сезонная сумма выводится только при покрытии даты начала сезона;
- автоматическая фенофаза не определяется.

Методическая основа: McMaster & Wilhelm, 1997, *Agricultural and Forest Meteorology*, 87(4), 291–300.

### ГТК Селянинова

```text
ГТК = 10 × ΣP / ΣTср
```

Используются только завершённые сутки с `Tср > 10°C`. Расчёт блокируется при коротком тёплом окне или недопустимой доле пропусков.

### Осадки − ET₀

Это диагностическая разность за завершённое окно, не баланс корнеобитаемого слоя и не доза полива. ET₀ поступает от провайдера.

### Температурный риск

Используется прогнозная суточная Tmin воздуха на высоте 2 м. Скрининг не определяет точный час минимума, температуру растений, вероятность ущерба или crop-specific порог повреждения.

## 🚀 Установка без Docker

Поддерживаются Debian, Ubuntu и совместимые Astra Linux окружения.

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo bash scripts/deploy.sh
```

Первый запуск создаёт PostgreSQL, Redis, пользователя `cropbot` и конфигурацию:

```text
/etc/crop-forecast-bot.env
```

Задайте токен и повторите установку:

```bash
sudo editor /etc/crop-forecast-bot.env
sudo bash scripts/deploy.sh
```

Неинтерактивный вариант:

```bash
sudo install -m 600 /dev/null /root/cropbot-token
sudo editor /root/cropbot-token
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

## 🛠 Команды администратора

```bash
# Диагностика
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh

# Проверка release
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh

# Read-only smoke реального Open-Meteo
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh \
  --live-provider 55.75 37.62 2026-04-15

# Логи и перезапуск
sudo journalctl -u crop-forecast-bot -f
sudo systemctl restart crop-forecast-bot

# Обновление и откат
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

### Скрипты

| Скрипт | Назначение |
|---|---|
| `scripts/deploy.sh` | зависимости, БД, Redis, release и systemd |
| `scripts/update.sh` | backup, новый release, миграции, preflight и auto-rollback |
| `scripts/rollback.sh` | возврат предыдущего либо указанного release |
| `scripts/status.sh` | service, commit, heartbeat, PostgreSQL, Redis и журнал |
| `scripts/verify-production.sh` | ruff, compileall, pytest, Alembic, Bash и optional live provider smoke |
| `scripts/help.sh` | краткая справка по командам |

## 🔄 Безопасное обновление

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
```

Последовательность:

```text
PostgreSQL dump
→ отдельный release
→ новый virtualenv
→ pip check / compileall
→ alembic upgrade head
→ runtime preflight
→ atomic current switch
→ systemd + heartbeat check
→ code rollback при ошибке
```

Миграции БД автоматически назад не откатываются. Перед update создаётся backup.

## ⚙️ Основная конфигурация

| Переменная | Назначение |
|---|---|
| `APP_ENV` | `production` требует PostgreSQL и Redis |
| `TELEGRAM_BOT_TOKEN` | токен BotFather |
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `REDIS_URL` | FSM, leases и дедупликация |
| `COORDINATION_NAMESPACE` | префикс Redis-ключей |
| `SCHEDULER_TIMEZONE` | timezone scheduler |
| `HEARTBEAT_FILE` | heartbeat event loop |
| `OPEN_METEO_CACHE_PATH` | writable cache Open-Meteo |
| `RAG_ENABLED` | разрешить опциональный советник |
| `INSTALL_RAG_PROFILE` | устанавливать `requirements-rag.txt` |

Шаблон: [`.env.example`](.env.example).

## 📚 Опциональный RAG

```bash
pip install -r requirements-rag.txt
python -m src.knowledge.indexer --reset
```

```dotenv
RAG_ENABLED=true
INSTALL_RAG_PROFILE=1
LLM_PROVIDER=groq
GROQ_API_KEY=...
```

RAG работает только при наличии проиндексированных документов и не подменяет deterministic weather calculations. Подробнее: [`RAG_GUIDE.md`](RAG_GUIDE.md).

## 🧪 Проверки и разработка

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
python -m src.bot.main
```

Core-проверка:

```bash
bash scripts/verify-production.sh
```

CI дополнительно запускает реальные PostgreSQL и Redis системными сервисами, без Docker. Проверяются:

- Alembic adoption/backfill на PostgreSQL;
- partial unique indexes и row locking;
- field-level scheduler targets;
- атомарные Redis leases между независимыми клиентами;
- межклиентская дедупликация уведомлений;
- восстановление aiogram FSM после повторного открытия RedisStorage.

Локальный запуск integration tests:

```bash
export TEST_DATABASE_URL='postgresql+asyncpg://cropbot_test:cropbot_test@127.0.0.1:5432/crop_forecast_bot_test'
export TEST_REDIS_URL='redis://127.0.0.1:6379/15'
python -m pytest -q -m integration
```

Без этих переменных integration tests пропускаются.

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
  └─ optional RAG
```

Единственная точка запуска:

```bash
python -m src.bot.main
```

## 📍 Документация и этапы

- статус: [`docs/STATUS.md`](docs/STATUS.md);
- возможности: [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md);
- план: [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md);
- аудит: [`docs/AUDIT_2026-07-10.md`](docs/AUDIT_2026-07-10.md);
- история: [`CHANGELOG.md`](CHANGELOG.md);
- runbook: [`QUICK_START_GUIDE.md`](QUICK_START_GUIDE.md).
