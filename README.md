# 🌾 Crop Forecast Bot

Telegram-бот для оперативной агрометеорологической оценки:

```text
поле → культура → сезон → проверяемый отчёт → фоновые предупреждения
```

[![CI](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml/badge.svg)](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml)

**Стек:** Python 3.11+, aiogram 3.x, PostgreSQL, Redis, Alembic, APScheduler и systemd. Docker не используется.

## ✅ Что работает

- 🗺 несколько полей в одном Telegram-профиле;
- 📍 геолокация и ручной ввод координат;
- ✏️ создание, переименование, переключение и изменение координат;
- 🌱 отдельные культура, дата посева и наблюдаемая фаза каждого поля;
- 🌦 Open-Meteo Forecast API;
- 🗓 сезонный реанализ Open-Meteo Historical Weather API;
- 📈 сравнение завершённой части сезона с фиксированной ERA5-Land базой 1991–2020;
- 🌿 ГДД с crop-specific `Tbase`, контролем периода и пропусков;
- 💧 ГТК только для валидного завершённого тёплого окна;
- 🚿 диагностическая разность осадки − ET₀ без фиктивных нулей;
- 🌧 накопленные осадки и provider ET₀ с начала сезона или за доступный период;
- 📉 парная климатическая разность `ΣP−ΣET₀`, сухие серии и максимумы осадков за 1/5 суток;
- 🌡 скрининг прогнозной Tmin воздуха на высоте 2 м;
- 📨 отдельные настройки дайджеста и температурных алертов каждого поля;
- 🔒 Redis FSM, callback idempotency, renewable job leases и дедупликация;
- 🗃 обязательные Alembic-миграции;
- ♻️ Bash-установка, обновление, диагностика и откат через systemd;
- 📚 опциональная RAG-база знаний с отображением источников.

> Отсутствующие данные не заменяются эвристикой. «Нет валидной прогнозной Tmin» и «риск не выявлен» — разные состояния.

## 🧑‍🌾 Как пользоваться

1. Отправьте `/start`.
2. Откройте **«Мои поля»**.
3. Добавьте поле или выберите активное.
4. Выберите культуру.
5. Укажите дату посева/начала сезона.
6. При наличии наблюдения выберите фактическую фазу.
7. Нажмите **«Агроотчёт»**.

Активное поле используется для ручного отчёта и редактирования. **Фоновый scheduler контролирует каждое поле, для которого включён соответствующий тип уведомления**, независимо от того, активно оно сейчас в меню или нет.

### Команды

| Команда | Назначение |
|---|---|
| `/start` | главное меню |
| `/help` | пользовательская справка |
| `/cancel` | отмена ввода и очистка FSM |

## 📊 Что содержит отчёт

Отчёт отвечает на четыре вопроса:

1. **Что происходит** — температурный риск, теплообеспеченность, осадки и атмосферная испаряемость.
2. **Насколько надёжно** — источник, модельная конфигурация, период, покрытие и пропуски.
3. **Что проверить сейчас** — локальный прогноз, фазу и микрорельеф.
4. **Когда обновить оценку** — после нового прогноза или изменения состояния поля.

Типы данных разделены:

- `reanalysis` — прошлый ряд Historical Weather API;
- `operational_past` — завершённые прошлые локальные сутки Forecast API;
- `forecast` — текущие и будущие локальные сутки.

Отчёт показывает время получения данных ботом и политику кэша. Точный model run и пространственное разрешение не придумываются, если endpoint их не сообщает.

## 📐 Расчёты

### ГДД

```text
GDDday = max(0, min(Tmean, Tupper) − Tbase)
```

- единицы: `°C·сут`;
- строки до **локальной даты** посева исключаются;
- прошлый период и прогнозный прирост считаются отдельно;
- сезонная сумма заявляется только при наличии строки на дату начала и допустимой доле пропусков;
- автоматическая фенофаза не определяется.

Методическая основа: McMaster & Wilhelm, 1997, *Agricultural and Forest Meteorology*, 87(4), 291–300.

### ГТК Селянинова

```text
ГТК = 10 × ΣP / ΣTср
```

Используются только завершённые сутки с `Tср > 10°C`. Прогнозные осадки не входят в расчёт. При коротком окне или недопустимой доле пропусков показатель не публикуется.

### Осадки − ET₀

Короткое 7-суточное окно показывает диагностическую разность осадков и provider ET₀. Это не баланс корнеобитаемого слоя и не доза полива.

### Накопленные осадки и ET₀

Для заданной даты начала сезона рассчитываются:

- `ΣP` и `ΣET₀` по завершённым локальным суткам;
- `ΣP−ΣET₀` только по парным валидным датам;
- число сухих и влажных суток при пороге `1 мм/сут`;
- текущая на конец ряда и максимальная сухая серия;
- максимальная сумма осадков за 1 и 5 последовательных суток.

Прогнозные строки не входят в накопления. Сухие серии и 5-суточный максимум не публикуются при календарном разрыве или пропуске осадков. ET₀ остаётся характеристикой атмосферной испаряемости эталонной поверхности, а не фактической ET культуры. Методика и ограничения: [`docs/SCIENTIFIC_WATER_INDICATORS.md`](docs/SCIENTIFIC_WATER_INDICATORS.md).

### Сезон относительно ERA5-Land 1991–2020

При заданной дате сезона бот отдельно запрашивает фиксированную модель `era5_land` и сравнивает завершённый текущий период с окнами той же длины и той же календарной даты старта в 1991–2020 годах.

Показываются при достаточном качестве:

- аномалия средней температуры, °C;
- сумма осадков и ET₀ в процентах от реанализного среднего;
- аномалия ГДД, °C·сут;
- положение максимальной сухой серии;
- эмпирические процентили и фактическое число сопоставимых лет.

Требуется не менее 20 валидных исторических окон. Накопленные метрики не публикуются при пропуске хотя бы одного дня. Процент температуры от среднего не вычисляется, потому что отношение значений в °C физически некорректно. Процентиль не является вероятностью, а реанализная сетка не называется станционной климатической нормой. Методика: [`docs/SCIENTIFIC_CLIMATE_REFERENCE.md`](docs/SCIENTIFIC_CLIMATE_REFERENCE.md).

### Температурный риск

Используется прогнозная суточная Tmin воздуха на высоте 2 м.

Состояния:

```text
risk_detected
no_risk_in_valid_forecast
insufficient_forecast_data
```

При отсутствии валидной Tmin бот не показывает зелёный вывод «риска нет».

## ⛔ Что не заявляется

В production пока нет:

- прогноза урожайности или валидированной ML-модели;
- SPI/SPEI без отдельного длинного однородного pipeline и distribution fit;
- локального FAO-56 Penman–Monteith;
- фактической ET культуры, `Kc/Ks`, влагозапаса корнеобитаемого слоя или дозы полива;
- прямого CDS job/object-cache pipeline для ERA5-Land;
- production-интеграции SoilGrids, Sentinel-2 или MODIS;
- crop/phase-specific вероятности повреждения заморозком;
- автоматической фенофазы по непроверенным GDD-порогам;
- доз удобрений и препаратов без нормативного источника.

Матрица: [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md).

## 🚀 Установка без Docker

Поддерживаются Debian, Ubuntu и совместимые Astra Linux окружения.

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo bash scripts/deploy.sh
```

Первый запуск создаёт PostgreSQL, Redis, пользователя `cropbot` и файл:

```text
/etc/crop-forecast-bot.env
```

Укажите Telegram-токен и повторите установку:

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
# Состояние, heartbeat, БД, Redis и журнал
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh

# Полная проверка release
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
| `scripts/rollback.sh` | возврат предыдущего или выбранного release |
| `scripts/status.sh` | service, commit, heartbeat, PostgreSQL, Redis и журнал |
| `scripts/verify-production.sh` | Ruff, compileall, pytest, Alembic, Bash и live provider smoke |
| `scripts/help.sh` | краткая справка по командам |

## 🔄 Обновление

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
```

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

### Гарантии фоновых заданий

Scheduler продлевает Redis job lease независимо от длительности запроса к провайдеру. При потере token ownership текущий read/report отменяется, а новые поля не обрабатываются. После аварийного завершения процесса другой worker получает lock только после истечения TTL.

Уведомление дополнительно резервируется отдельным ключом Redis. Однако Telegram `sendMessage` не поддерживает idempotency key: если процесс погиб после принятия сообщения Telegram, но до фиксации dedup lease, абсолютная гарантия exactly-once невозможна. Бот не скрывает эту границу и не должен быть единственным каналом критических предупреждений.

## 🧪 Разработка и тесты

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
python -m src.bot.main
```

```bash
bash scripts/verify-production.sh
```

CI запускает PostgreSQL и Redis системными сервисами, без Docker. Проверяются миграции, row locks, Redis FSM restart, callback idempotency, два scheduler worker, продление job lease во время долгого I/O, восстановление после аварийного выхода процесса, атомарный rollback пользовательской операции, накопленные показатели и ERA5-Land reference contracts.

Локальные integration tests:

```bash
export TEST_DATABASE_URL='postgresql+asyncpg://cropbot_test:cropbot_test@127.0.0.1:5432/crop_forecast_bot_test'
export TEST_REDIS_URL='redis://127.0.0.1:6379/15'
python -m pytest -q -m integration
```

## 🏗 Архитектура

```text
Telegram handlers / Redis FSM
        ↓
application services + typed ports
        ↓
domain / bounded agro calculations
        ↓
infrastructure adapters
  ├─ Open-Meteo forecast + seasonal history + ERA5-Land reference
  ├─ PostgreSQL / Alembic
  ├─ Redis coordination
  └─ optional RAG
```

Единственная точка запуска:

```bash
python -m src.bot.main
```

## 📍 Документация

- [`docs/STATUS.md`](docs/STATUS.md) — выполнено и текущий этап;
- [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) — фактические возможности;
- [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md) — план модернизации;
- [`docs/SCIENTIFIC_WATER_INDICATORS.md`](docs/SCIENTIFIC_WATER_INDICATORS.md) — накопленные осадки, ET₀, сухие серии и ограничения;
- [`docs/SCIENTIFIC_CLIMATE_REFERENCE.md`](docs/SCIENTIFIC_CLIMATE_REFERENCE.md) — ERA5-Land 1991–2020, аномалии, процентили и ограничения;
- [`docs/AUDIT_2026-07-10.md`](docs/AUDIT_2026-07-10.md) — базовый аудит;
- [`CHANGELOG.md`](CHANGELOG.md) — история изменений;
- [`QUICK_START_GUIDE.md`](QUICK_START_GUIDE.md) — эксплуатационный runbook.
