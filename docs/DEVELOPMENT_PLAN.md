# План модернизации Crop Forecast Bot

## Целевая архитектура

```text
Telegram
  -> aiogram handlers / FSM
      -> application services
          -> domain/agro calculations
              -> infrastructure
                  -> Open-Meteo / ERA5 / SoilGrids / satellite providers
                  -> PostgreSQL repositories
                  -> Redis FSM/cache/locks
                  -> RAG adapters
```

Правила:

- один Telegram framework: aiogram 3.x;
- один production entrypoint: `python -m src.bot.main`;
- handlers не выполняют HTTP, расчёты, файловые операции и блокирующие вызовы;
- все I/O-контракты async и типизированы;
- PostgreSQL — source of truth, Redis — FSM/cache/locks;
- любой fallback виден пользователю и не повышает заявленную точность;
- формулы имеют источник, единицы, период применимости и тесты;
- релиз принимается только после CI и container smoke test.

## Этап 0 — аварийная стабилизация runtime

Статус: **выполнено в PR модернизации 2026-07-10**.

- [x] удалить telebot entrypoint и конфликтующий handlers module;
- [x] подключить основной aiogram Router/FSM;
- [x] перенести поле, координаты, культуру, отчёт и уведомления;
- [x] убрать глобальные user state dictionaries;
- [x] унифицировать Open-Meteo DTO и async API;
- [x] исправить DB session contract scheduler;
- [x] согласовать frost result и formatter;
- [x] добавить startup/shutdown БД, bot session, storage, scheduler;
- [x] добавить Redis FSM fallback policy;
- [x] заменить фиктивный healthcheck heartbeat-проверкой;
- [x] обновить Docker/Compose/.env;
- [x] добавить deploy/update/systemd scripts;
- [x] добавить первый CI и unit tests.

Критерий готовности: основной Telegram путь работает из aiogram entrypoint; CI зелёный; Docker image собирается.

## Этап 1 — миграции и надёжность состояния

Приоритет: P0.

- [ ] создать Alembic baseline из фактической модели;
- [ ] убрать `Base.metadata.create_all()` из production startup;
- [ ] добавить поля field/season:
  - идентификатор и название поля;
  - timezone;
  - elevation source;
  - crop;
  - sowing/season start date;
  - phenological phase and confidence;
  - notification preferences;
- [ ] перенести alert deduplication в Redis `SET NX EX`;
- [ ] добавить distributed scheduler lock;
- [ ] обработать restart во время FSM;
- [ ] интеграционные тесты PostgreSQL/Redis через testcontainers.

Критерий готовности: рестарт процесса не теряет пользовательский прогресс и не дублирует уведомления.

## Этап 2 — provider layer

Приоритет: P0/P1.

- [ ] ввести provider interfaces и DTO для forecast, observations, reanalysis, soil and satellite;
- [ ] единая metadata model: source, model, run time, valid time, update time, resolution, fallback quality;
- [ ] общий HTTP client lifecycle;
- [ ] timeout, retry with jitter, rate limit, circuit breaker, cache policy;
- [ ] Open-Meteo integration tests via mocked responses;
- [ ] SoilGrids validation including ocean/no-data;
- [ ] ERA5-Land job state, CDS queue and cache integrity;
- [ ] Sentinel/MODIS provider selected only after checking actual access and quotas;
- [ ] remove or isolate Google Earth Engine dependency if credentials are not part of supported deployment.

Критерий готовности: provider outage yields controlled degraded output, not a fabricated recommendation.

## Этап 3 — научный расчётный слой

Приоритет: P0.

### ГДД

- [ ] configurable sowing/season start;
- [ ] crop-specific `Tbase` and optional upper cutoff;
- [ ] distinguish observed/reanalysis/forecast contribution;
- [ ] validate phenology thresholds by crop and region;
- [ ] tests for missing values, leap year, DST and season boundaries.

### ГТК

- [ ] calculate only over a valid vegetation period with Tmean > 10°C;
- [ ] use a season-consistent observation/reanalysis series;
- [ ] expose number of valid days and missing-data fraction;
- [ ] do not combine a 14-day archive with a season label.

### ET0 and water balance

- [ ] preserve provider ET0 as provider data;
- [ ] optional local FAO-56 Penman–Monteith implementation with complete inputs;
- [ ] crop coefficient and root-zone model only with explicit stage and soil context;
- [ ] no irrigation dose without verified agronomic context.

### Frost

- [ ] crop and phase susceptibility thresholds;
- [ ] local time and terrain correction;
- [ ] air/surface temperature distinction;
- [ ] ensemble/probabilistic uncertainty where available;
- [ ] alert validation metrics: POD, FAR, CSI, lead time.

### SPI

- [ ] long homogeneous monthly precipitation series;
- [ ] distribution fitting and goodness-of-fit checks;
- [ ] never compute from a short forecast window.

Критерий готовности: every displayed indicator has source, units, valid period, uncertainty note and tests.

## Этап 4 — Telegram UX

Приоритет: P1.

- [ ] three-step main flow: field -> crop -> report;
- [ ] back/cancel on every FSM branch;
- [ ] duplicate callback protection and idempotency keys;
- [ ] compact reports with four sections:
  1. what is happening;
  2. reliability;
  3. what to do now;
  4. when to check again;
- [ ] explicit progress without unsupported duration promises;
- [ ] settings for timezone, season date and notification windows;
- [ ] administrator diagnostics: provider status, queue, alerts and error report export;
- [ ] scenario tests using aiogram test utilities/mocks.

Критерий готовности: complete scenario is reachable from `/start` and survives restart.

## Этап 5 — RAG and recommendations

Приоритет: P1/P2.

- [ ] lazy RAG initialization;
- [ ] optional deployment profile for heavy embeddings;
- [ ] document metadata, version, page and citation validation;
- [ ] no agronomic dose or pesticide recommendation without a normative source and context;
- [ ] prompt-injection resistance and source-only mode;
- [ ] evaluation set for Russian agronomy questions;
- [ ] remove claims about model accuracy until real independent validation exists.

Критерий готовности: every material recommendation is attributable to a retrieved source or a transparent deterministic calculation.

## Этап 6 — operations and release engineering

Приоритет: P1.

- [ ] generate and commit `uv.lock` after target-platform resolution;
- [ ] multi-profile dependencies: core, climate, satellite, rag, dev;
- [ ] Alembic migration in deploy/update scripts;
- [ ] Compose smoke test with mocked Telegram endpoint;
- [ ] backup/restore runbook for PostgreSQL and Redis;
- [ ] JSON logging, request correlation ID and error metrics;
- [ ] Prometheus/OpenTelemetry or a minimal health/metrics endpoint;
- [ ] release tags and changelog;
- [ ] rollback command that restores code and verifies schema compatibility;
- [ ] test on Debian 12 and Astra Linux 1.7.

Критерий готовности: a clean host can be installed, updated and rolled back using documented commands without manual code edits.

## Definition of Done ближайшего релиза

- один aiogram entrypoint;
- основной пользовательский сценарий доступен из Telegram;
- PostgreSQL, Redis and scheduler contracts covered by integration tests;
- Open-Meteo failure has explicit degraded behavior;
- ГТК/ГДД/ET0/frost are period-correct and scientifically labelled;
- Alembic migration is mandatory on startup/update;
- Docker/Compose and systemd startup pass smoke tests;
- CI has no failing test, type or security checks;
- no telebot, global user state or unsupported accuracy claims remain.
