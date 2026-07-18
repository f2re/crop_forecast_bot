# 🌾 Crop Forecast Bot

Telegram-бот для проверяемой агрометеорологической оценки:

```text
поле → культура → сезон → отчёт → риски → история сигнала
```

[![CI](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml/badge.svg)](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml)

**Стек:** Python 3.11+, aiogram 3.x, PostgreSQL, Redis, Alembic, APScheduler и systemd. Docker не используется.

## Что работает

- несколько полей в одном Telegram-профиле;
- геолокация и ручной ввод координат;
- культура, дата сезона и наблюдаемая фаза для каждого поля;
- оперативный агроотчёт Open-Meteo;
- сезонная история и homogeneous ERA5-Land comparison с базой 1991–2020;
- GDD, сезонный ГТК, provider ET₀, `P−ET₀`, накопленные осадки, сухие серии, Rx1day/Rx5day;
- GFS Ensemble screening до 16 суток;
- риски холода, жары, сильных осадков, ветра и конвективной неустойчивости;
- ручной обзор рисков `/risks`;
- фоновый анализ каждые 6 часов;
- persistent history запусков и сигналов;
- тренд `/history`: новый, усиливается, стабилен, ослабевает, снят;
- Redis FSM, callback idempotency, renewable leases и deduplication;
- versioned systemd releases, heartbeat, verified rollback;
- PostgreSQL backup/restore verification;
- live Open-Meteo, ERA5-Land и GFS contracts;
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

Активное поле используется для ручных действий. Фоновый scheduler контролирует каждое поле, для которого включены уведомления, независимо от текущего активного поля.

### Команды

| Команда | Назначение |
|---|---|
| `/start` | главное меню |
| `/risks` | ручной обзор ансамблевых погодных рисков |
| `/history` | изменение сигналов между последними запусками |
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

Сутки принимаются только при достаточном количестве членов по всем пяти диагностическим переменным. Отчёт показывает:

- `k/n` членов, пересёкших операционный порог;
- P10, медиану и P90;
- заблаговременность;
- модель, источник и покрытие;
- практическую проверку и научное ограничение.

`k/n` — сырая доля модельных сценариев, а не откалиброванная вероятность. CAPE показывает потенциальную конвективную среду и не является прогнозом грозы или града.

## История и тренд

Accepted ensemble runs сохраняются в PostgreSQL:

```text
risk_forecast_runs
risk_forecast_signals
```

Run и его signals фиксируются одной транзакцией до Telegram side effect. Повтор одного provider response идемпотентен по:

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

`/history` сравнивает два последних запуска одной модели для одинаковых `risk_type + event_date`:

- `new`;
- `strengthening`;
- `stable`;
- `weakening`;
- `cleared`.

Изменение уровня имеет приоритет; внутри одного уровня существенным считается изменение доли на 10 процентных пунктов. Это тренд модельного сигнала, а не вероятность события или ущерба.

Retention задаётся:

```dotenv
RISK_HISTORY_RETENTION_DAYS=90
```

## Агрометеорологические расчёты

### GDD

```text
GDDday = max(0, min((Tmax + Tmin) / 2, Tupper) − Tbase)
```

- единицы: `°C·сут`;
- строки до локальной даты сезона исключаются;
- завершённый период и forecast increment считаются отдельно;
- автоматическая фенофаза не определяется.

### ГТК Селянинова

```text
ГТК = 10 × ΣP / ΣTср
```

Условия публикации:

- задана локальная дата сезона;
- используются только завершённые сутки;
- `Tср > 10°C`;
- минимум 20 тёплых суток;
- непрерывный календарный ряд;
- forecast precipitation исключён;
- отрицательные осадки считаются отсутствующими данными.

Универсальная классификация засухи не генерируется.

### Осадки и ET₀

Показываются:

- короткая диагностическая разность `P−ET₀`;
- накопленные `ΣP` и provider `ΣET₀`;
- парная `ΣP−ΣET₀`;
- сухие/влажные сутки при пороге 1 мм/сут;
- текущая и максимальная сухая серия;
- Rx1day и bounded Rx5day.

ET₀ — reference evapotranspiration, не фактическая ET культуры. `P−ET₀` не является влагозапасом или дозой полива.

### ERA5-Land 1991–2020

Текущий сезон сравнивается с окнами той же длины и календарной даты старта одной модели `era5_land`. Требуется минимум 20 валидных reference-лет. Empirical percentile не является вероятностью, SPI/SPEI или станционной климатической нормой.

Методики:

- `docs/SCIENTIFIC_FORMULA_AUDIT_2026-07-17.md`;
- `docs/SCIENTIFIC_WATER_INDICATORS.md`;
- `docs/SCIENTIFIC_CLIMATE_REFERENCE.md`;
- `docs/ENSEMBLE_RISK_METHODOLOGY.md`.

## Что не заявляется

В production-code нет:

- валидированного прогноза урожайности;
- SPI/SPEI по короткому прогнозу;
- crop/phase damage model;
- вероятности града;
- локального FAO-56 Penman–Monteith;
- validated `Kc/Ks` и root-zone water balance;
- SoilGrids/Sentinel/MODIS production adapters;
- доз препаратов или удобрений без нормативного источника.

Фактическая матрица: `docs/CAPABILITIES.md`.

## Установка без Docker

Поддерживаемый deployment path:

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo bash scripts/deploy.sh
```

Первый запуск создаёт runtime user, PostgreSQL, Redis, versioned release и environment file:

```text
/etc/crop-forecast-bot.env
```

Укажите Telegram token и повторите deploy:

```bash
sudo editor /etc/crop-forecast-bot.env
sudo bash scripts/deploy.sh
```

Неинтерактивный token path:

```bash
sudo install -m 600 /dev/null /root/cropbot-token
sudo editor /root/cropbot-token
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

## Администрирование

```bash
# service, heartbeat, DB, Redis, release и журнал
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh

# локальный release verification
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh

# Open-Meteo + ERA5-Land live checks
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh \
  --live-all 55.75 37.62 2026-04-15 wheat

# backup restore verification
sudo bash \
  /opt/crop-forecast-bot/current/scripts/verify-backup-restore.sh

# update / rollback
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh

# logs
sudo journalctl -u crop-forecast-bot -f
```

Production запускается:

```bash
python -m src.bot.main
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

CI также выполняет ShellCheck, repository policies, PostgreSQL/Redis integration и backup/restore.

## Граница готовности

Код, CI и live provider contracts подтверждены. До статуса «готов к самостоятельной эксплуатации в поле» обязательны:

- clean Debian 12 install/reboot/update/rollback;
- real Telegram smoke для нескольких пользователей и полей;
- Astra Linux smoke;
- station comparison;
- screening-only регламент и резервный канал критических предупреждений.

Статус: `docs/STATUS.md`.  
План: `docs/DEVELOPMENT_PLAN.md`.  
Технический аудит: `docs/TECHNICAL_AUDIT_2026-07-18.md`.
