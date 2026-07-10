# 🌾 Crop Forecast Bot

Telegram-бот для оперативной агрометеорологической оценки полей:
**поле → культура → сезон → проверяемый отчёт → уведомления**.

[![CI](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml/badge.svg)](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml)

**Production:** Python 3.11+, aiogram 3.x, PostgreSQL, Redis, Alembic и systemd. Docker не используется.

## ✅ Что реально работает

- 🗺 несколько полей в одном Telegram-профиле;
- 📍 геолокация и ручной ввод координат;
- ✏️ создание, переименование, переключение и изменение координат поля;
- 🌱 отдельные культура, дата посева и фактическая фаза каждого поля;
- 🌦 оперативный прогноз Open-Meteo;
- 🗓 сезонный ряд реанализа Open-Meteo Historical Weather API;
- 🌿 ГДД с crop-specific `Tbase`, контролем покрытия и пропусков;
- 💧 ГТК Селянинова только для валидного завершённого тёплого окна;
- 🚿 разность осадки − ET₀ провайдера без подстановки фиктивных нулей;
- 🌡 скрининг прогнозной Tmin воздуха на высоте 2 м;
- 📨 независимые ежедневные отчёты и температурные алерты для активного поля;
- 🔒 Redis FSM, распределённые блокировки и дедупликация уведомлений;
- 🗃 обязательные Alembic-миграции;
- ♻️ Bash-установка, обновление, диагностика и откат через systemd;
- 📚 опциональная RAG-база знаний с отображением источников.

> Бот не подменяет отсутствующие данные эвристикой. При недоступности провайдера или неполном ряде показатель не рассчитывается либо явно помечается как ограниченный.

## ⛔ Что намеренно не заявляется

В production сейчас **нет**:

- прогноза урожайности или валидированной ML-модели;
- SPI по короткому прогнозу;
- локального расчёта FAO-56 Penman–Monteith;
- production-интеграции SoilGrids, Sentinel-2, MODIS или Google Earth Engine;
- crop/phase-specific вероятности повреждения заморозком;
- автоматического определения фенофазы по непроверенным GDD-порогам;
- рекомендаций доз удобрений и препаратов без нормативного источника.

Подробная матрица: [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md).

## 🧑‍🌾 Работа в Telegram

1. Отправьте `/start`.
2. Откройте **«Мои поля»**.
3. Добавьте поле или сделайте существующее активным.
4. Выберите культуру активного поля.
5. Укажите дату посева/начала сезона.
6. При наличии полевого наблюдения выберите фактическую фазу.
7. Нажмите **«Агроотчёт»**.

У каждого поля независимо сохраняются координаты, культура, сезон, фаза и настройки уведомлений. Ручной отчёт и scheduler работают с активным полем.

### Команды

| Команда | Назначение |
|---|---|
| `/start` | главное меню и активное поле |
| `/help` | пользовательская справка |
| `/cancel` | отмена текущего ввода и очистка FSM |

## 📊 Что содержит отчёт

Отчёт отвечает на четыре вопроса:

1. **Что происходит** — температурный риск, ГДД и влагообеспеченность.
2. **Насколько надёжно** — источник, период, покрытие и пропуски.
3. **Что проверить сейчас** — локальный прогноз, фазу и микрорельеф.
4. **Когда обновить оценку** — после нового прогноза или изменения состояния поля.

Источники не смешиваются:

- `reanalysis` — прошлый ряд Historical Weather API;
- `operational_past` — завершённые прошлые локальные сутки Forecast API;
- `forecast` — текущие и будущие локальные сутки.

Текущий локальный день не считается завершённым прошлым периодом.

## 📐 Расчёты и ограничения

### ГДД

```text
GDDday = max(0, min(Tmean, Tupper) − Tbase)
```

- единицы: `°C·сут`;
- `Tbase` берётся из единого каталога культур;
- `Tupper` применяется только при явной настройке;
- завершённый период и прогнозный прирост считаются отдельно;
- сезонная сумма выводится только при покрытии даты начала сезона;
- автоматическая фенофаза не определяется.

Методическая основа: McMaster & Wilhelm, 1997, *Agricultural and Forest Meteorology*, 87(4), 291–300.

### ГТК Селянинова

```text
ГТК = 10 × ΣP / ΣTср, только для завершённых суток с Tср > 10°C
```

Расчёт блокируется при недостаточном числе тёплых суток или слишком большой доле пропусков. Универсальная классификация без культуры, региона и периода не выдаётся.

### Осадки − ET₀

Это диагностическая разность за завершённое окно, а не баланс корнеобитаемого слоя и не доза полива. ET₀ поступает от Open-Meteo как provider variable.

### Температурный риск

Используется прогнозная суточная Tmin воздуха на высоте 2 м. Скрининг не определяет точный час минимума, температуру растений, вероятность ущерба или crop-specific порог повреждения.

## 🚀 Установка без Docker

Поддерживается нативная установка на Debian, Ubuntu и совместимые Astra Linux окружения.

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo bash scripts/deploy.sh
```

Первый запуск создаст PostgreSQL, Redis, пользователя `cropbot` и защищённую конфигурацию:

```text
/etc/crop-forecast-bot.env
```

Задайте Telegram-токен и повторите установку:

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

## 🛠 Шпаргалка администратора

```bash
# Полная диагностика
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh

# Проверка кода, миграций и тестов
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh

# Дополнительный read-only smoke реального Open-Meteo
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh \
  --live-provider 55.75 37.62 2026-04-15

# Логи
sudo journalctl -u crop-forecast-bot -f

# Перезапуск
sudo systemctl restart crop-forecast-bot

# Обновление
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main

# Откат к предыдущей версии
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

### Эксплуатационные скрипты

| Скрипт | Назначение |
|---|---|
| `scripts/deploy.sh` | системные зависимости, БД, Redis, release и systemd |
| `scripts/update.sh` | backup, новый release, миграции, preflight и auto-rollback |
| `scripts/rollback.sh` | возврат предыдущего либо указанного release |
| `scripts/status.sh` | service, commit, heartbeat, PostgreSQL, Redis и журнал |
| `scripts/verify-production.sh` | ruff, compileall, pytest, Alembic, Bash и optional live provider smoke |
| `scripts/help.sh` | готовая справка по командам |

## 🔄 Безопасное обновление

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
```

Порядок:

1. PostgreSQL dump;
2. отдельный release-каталог;
3. новый virtualenv;
4. установка выбранного dependency profile;
5. `pip check` и `compileall`;
6. `alembic upgrade head`;
7. runtime preflight;
8. атомарное переключение `current`;
9. проверка systemd и heartbeat;
10. автоматический возврат предыдущего кода при неуспехе.

Миграции БД автоматически назад не откатываются. Перед update создаётся backup.

## ⚙️ Основная конфигурация

| Переменная | Назначение |
|---|---|
| `APP_ENV` | `production` требует PostgreSQL и Redis |
| `TELEGRAM_BOT_TOKEN` | обязательный токен BotFather |
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `REDIS_URL` | FSM, leases и дедупликация |
| `COORDINATION_NAMESPACE` | префикс Redis-ключей |
| `SCHEDULER_TIMEZONE` | timezone scheduler |
| `HEARTBEAT_FILE` | heartbeat event loop |
| `OPEN_METEO_CACHE_PATH` | writable cache Open-Meteo |
| `RAG_ENABLED` | показать и разрешить опциональный советник |
| `INSTALL_RAG_PROFILE` | устанавливать `requirements-rag.txt` при deploy/update |

Шаблон: [`.env.example`](.env.example).

## 📚 Опциональный RAG

Базовый бот не устанавливает тяжёлые embeddings-зависимости.

```bash
pip install -r requirements-rag.txt
python -m src.knowledge.indexer --reset
```

Затем настройте, например:

```dotenv
RAG_ENABLED=true
INSTALL_RAG_PROFILE=1
LLM_PROVIDER=groq
GROQ_API_KEY=...
```

RAG работает только при наличии проиндексированных документов. Ответ сопровождается найденными источниками; отсутствие источника не подменяется свободной генерацией. Подробнее: [`RAG_GUIDE.md`](RAG_GUIDE.md).

## 🧪 Локальная разработка

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
python -m src.bot.main
```

Полная проверка:

```bash
bash scripts/verify-production.sh
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
  └─ optional RAG
```

Единственная точка запуска:

```bash
python -m src.bot.main
```

## 📍 Состояние разработки

- текущий статус: [`docs/STATUS.md`](docs/STATUS.md);
- фактические возможности: [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md);
- план этапов: [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md);
- аудит: [`docs/AUDIT_2026-07-10.md`](docs/AUDIT_2026-07-10.md);
- история изменений: [`CHANGELOG.md`](CHANGELOG.md);
- эксплуатационный runbook: [`QUICK_START_GUIDE.md`](QUICK_START_GUIDE.md).
