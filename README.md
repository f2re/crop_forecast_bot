# 🌾 Crop Forecast Bot

Telegram-бот для проверяемой агрометеорологической оценки:

```text
поле → культура → сезон → отчёт → риски → история → настройки доставки
```

[![CI](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml/badge.svg)](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml)

**Стек:** Python 3.11+, aiogram 3.x, PostgreSQL, Redis, Alembic, APScheduler и systemd. Docker не используется.

## Что работает

- несколько полей в одном Telegram-профиле;
- геолокация и ручной ввод координат;
- культура, дата сезона и наблюдаемая фаза каждого поля;
- оперативный агроотчёт Open-Meteo Forecast Best Match;
- bounded seasonal history Open-Meteo Historical Weather;
- homogeneous ERA5 comparison с базой 1991–2020;
- GDD, сезонный ГТК, provider ET₀, `P−ET₀`, накопления, dry spells, Rx1day/Rx5day;
- GFS Ensemble screening до 16 суток;
- риски холода, жары, сильных осадков, ветра и конвективной среды;
- ручной обзор `/risks`;
- history/trend `/history`;
- background monitoring каждые 6 часов;
- один compact multi-hazard digest на поле;
- режимы `immediate / digest / high_only`;
- локальные тихие часы с high-risk bypass;
- Redis FSM, callback idempotency, renewable leases и deduplication;
- versioned systemd releases, heartbeat и verified rollback;
- PostgreSQL backup/restore verification;
- live Open-Meteo, ERA5 и GFS contracts;
- optional source-attributed RAG.

> Пропуск данных не заменяется эвристикой. «Недостаточно данных» и «риск не выявлен» — разные состояния.

## Пользовательский сценарий

1. Отправьте `/start`.
2. Откройте **«Мои поля»**.
3. Добавьте поле или выберите активное.
4. Выберите культуру.
5. Укажите дату посева/начала сезона.
6. При наличии наблюдения укажите фактическую фазу.
7. Откройте **«Агроотчёт»**, **«Погодные риски»** или **«История рисков»**.
8. В **«Уведомлениях»** выберите режим и тихие часы.

Активное поле используется для ручных действий. Background scheduler контролирует каждое поле, для которого включены alerts.

### Команды

| Команда | Назначение |
|---|---|
| `/start` | главное меню |
| `/risks` | ручной обзор ансамблевых рисков |
| `/history` | изменение сигналов между запусками |
| `/help` | пользовательская справка |
| `/cancel` | отмена текущего FSM-ввода |

## Погодные риски

Используются отдельные члены NOAA GFS Ensemble через Open-Meteo Ensemble API.

Для каждой локальной даты анализируются:

- Tmin воздуха 2 м;
- Tmax воздуха 2 м;
- суточные осадки;
- максимальный порыв ветра 10 м;
- CAPE max.

Сутки принимаются только при достаточном количестве членов по всем пяти переменным. Пользователь видит:

- `k/n` членов, пересёкших операционный порог;
- P10, медиану и P90;
- lead time;
- модель, источник и coverage;
- практическую проверку;
- scientific caveat.

`k/n` — сырая доля модельных сценариев, а не calibrated probability. CAPE показывает потенциальную конвективную среду и не является прогнозом грозы или града.

## Доставка рисков

На уровне каждого поля доступны:

```text
immediate  — сообщение при новом/существенно изменившемся состоянии
digest     — один обычный digest в локальные сутки
high_only  — только level=high
```

Тихие часы:

```text
off
22:00–07:00
23:00–06:00
```

Watch/elevated events откладываются в quiet hours. High risk отправляется без ожидания тихих часов или daily digest.

Accepted run всегда сохраняется до delivery decision. Quiet hours не превращают результат в «риска нет» и не удаляют history.

## История и тренд

Accepted ensemble runs сохраняются в PostgreSQL:

```text
risk_forecast_runs
risk_forecast_signals
```

Run и signals фиксируются одной транзакцией до Telegram side effect. Повтор provider response идемпотентен по:

```text
field_id + model + retrieved_at
```

Delivery state:

```text
not_attempted
sending
sent
deduplicated
failed
```

`/history` сравнивает два последних запуска одной модели:

```text
new
strengthening
stable
weakening
cleared
```

Это trend model signal, а не вероятность события или ущерба.

Retention:

```dotenv
RISK_HISTORY_RETENTION_DAYS=90
```

## Агрометеорологические расчёты

### GDD

```text
GDDday = max(0, min((Tmax + Tmin) / 2, Tupper) − Tbase)
```

- единицы: `°C·сут`;
- строки до local season date исключаются;
- completed period и forecast increment считаются отдельно;
- automatic phenology не определяется.

### ГТК Селянинова

```text
ГТК = 10 × ΣP / ΣTср
```

Условия:

- задана локальная дата сезона;
- только completed days;
- `Tср > 10°C`;
- минимум 20 тёплых суток;
- непрерывный calendar series;
- forecast precipitation исключён;
- negative precipitation считается missing.

Universal drought class не генерируется.

### Осадки и ET₀

Показываются:

- short `P−ET₀` diagnostic;
- accumulated `ΣP` и provider `ΣET₀`;
- paired `ΣP−ΣET₀`;
- dry/wet days при 1 мм/сут;
- current/max dry spell;
- Rx1day и bounded Rx5day.

ET₀ — reference evapotranspiration, не фактическая ET культуры. `P−ET₀` не является root-zone storage или irrigation dose.

### ERA5 1991–2020

Current season сравнивается с окнами одинаковой длины и даты старта одной fixed model `era5`.

Climate DTO содержит только общий непрерывный period, полный одновременно по:

```text
Tmean
precipitation
ET0
```

Номинальная ERA5-сетка около 25 км. Это не полевая станция и не характеристика конкретного участка.

Требуется минимум 20 reference years. Empirical percentile не является probability, SPI/SPEI или station normal.

Методики:

- `docs/SCIENTIFIC_FORMULA_AUDIT_2026-07-17.md`;
- `docs/SCIENTIFIC_WATER_INDICATORS.md`;
- `docs/SCIENTIFIC_CLIMATE_REFERENCE.md`;
- `docs/ENSEMBLE_RISK_METHODOLOGY.md`.

## Что не заявляется

В production-code нет:

- validated yield forecast;
- SPI/SPEI по короткому прогнозу;
- crop/phase damage model;
- calibrated hail probability;
- local FAO-56 Penman–Monteith;
- validated `Kc/Ks` и root-zone water balance;
- SoilGrids/Sentinel/MODIS production adapters;
- pesticide/fertilizer doses без нормативного источника.

Фактическая матрица: `docs/CAPABILITIES.md`.

## Установка без Docker

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo bash scripts/deploy.sh
```

Первый запуск создаёт runtime user, PostgreSQL, Redis, versioned release и:

```text
/etc/crop-forecast-bot.env
```

Укажите Telegram token и повторите deploy:

```bash
sudo editor /etc/crop-forecast-bot.env
sudo bash scripts/deploy.sh
```

Production entrypoint:

```bash
python -m src.bot.main
```

## Администрирование

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
sudo -u cropbot bash /opt/crop-forecast-bot/current/scripts/verify-production.sh
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh \
  --live-all 55.75 37.62 2026-04-15 wheat
sudo bash /opt/crop-forecast-bot/current/scripts/verify-backup-restore.sh
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
sudo journalctl -u crop-forecast-bot -f
```

## Проверки разработчика

```bash
pip install -r requirements-dev.txt
ruff check src config alembic tests
python -m compileall -q alembic config src tests
python -m pytest -q -m "not integration"
TEST_DATABASE_URL=... TEST_REDIS_URL=... \
  python -m pytest -q -m integration
python -m alembic heads
```

CI также выполняет ShellCheck, repository policies, PostgreSQL/Redis integration, backup/restore, live provider contracts и сохраняет pytest logs как artifacts.

## Граница готовности

До статуса «готов к самостоятельной эксплуатации в поле» обязательны:

- clean Debian 12 install/reboot/update/rollback;
- real Telegram smoke;
- Astra Linux smoke;
- station comparison;
- screening-only operating protocol;
- independent official warning channel.

Статус: `docs/STATUS.md`.  
План: `docs/DEVELOPMENT_PLAN.md`.  
Глубокий аудит: `docs/DEEP_AUDIT_2026-07-19.md`.
