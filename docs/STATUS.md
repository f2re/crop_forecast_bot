# Статус разработки

Дата актуализации: **2026-07-12**.

Текущий `main`: field-readiness срез слит через PR #21.

## Текущий production-контур

```text
aiogram 3.x
PostgreSQL + Alembic
Redis FSM / callback idempotency / leases / deduplication
Open-Meteo Forecast + Historical Weather
APScheduler
systemd + Bash release scripts
```

## Выполнено

### Runtime и эксплуатация

- [x] один entrypoint `python -m src.bot.main`;
- [x] native deploy/update/rollback/status без Docker;
- [x] systemd readiness, heartbeat и watchdog;
- [x] atomic releases и PostgreSQL backup;
- [x] обязательный Alembic head на startup;
- [x] полный CI для `src/config/alembic/tests`;
- [x] реальные PostgreSQL и Redis в CI.

### Telegram и состояние

- [x] несколько полей;
- [x] геолокация и ручные координаты;
- [x] культура, дата сезона и ручная фаза;
- [x] отдельные настройки уведомлений каждого поля;
- [x] Redis FSM restart;
- [x] callback delivery idempotency;
- [x] подавление rapid double-click;
- [x] desired-state callback вместо toggle;
- [x] race-safe создание пользователя через upsert;
- [x] первичное создание поля под row lock.

### Источники и расчёты

- [x] typed weather DTO и provider port;
- [x] раздельные `reanalysis / operational_past / forecast`;
- [x] текущий локальный день не считается завершённым прошлым;
- [x] ГДД строго от локальной даты начала сезона;
- [x] ГТК без прогнозных осадков;
- [x] P−ET₀ без подстановки нулей;
- [x] frost screening только по прогнозным строкам;
- [x] `insufficient_forecast_data` отделён от `no_risk`;
- [x] fail-closed предупреждение при недоступной Tmin;
- [x] модельная конфигурация, время получения и cache policy в metadata;
- [x] неподдерживаемые научные функции выключены.

### Scheduler

- [x] distributed job locks;
- [x] field/day/event deduplication;
- [x] два worker не дублируют alert/digest;
- [x] retry после неуспешной Telegram-отправки;
- [x] фоновые задания охватывают все включённые поля;
- [x] ежедневный отчёт проверяется в локальном утреннем окне поля;
- [x] предупреждение о недоступной Tmin дедуплицируется по полю и дате.

### Field-readiness verification

- [x] Ruff, compileall, unit и integration CI;
- [x] concurrent PostgreSQL onboarding;
- [x] all-field scheduler targets;
- [x] regression test против false no-risk;
- [x] PR #21 слит в `main` после зелёного CI.

## Текущий этап

### P0 — полный Telegram/FSM flow и отказные сценарии

- [ ] полный Router/FSM test `field → crop → season → report`;
- [ ] restart test каждой FSM-ветки;
- [ ] outage PostgreSQL/Redis во время пользовательской операции;
- [ ] scheduler worker crash / lease-loss orchestration;
- [ ] callback после удаления или редактирования исходного сообщения.

### P0 — clean-host эксплуатация

- [ ] `deploy → update → forced failure → rollback` на Debian 12;
- [ ] восстановление PostgreSQL dump в отдельную БД;
- [ ] реальный Telegram API smoke для двух полей;
- [ ] smoke на поддерживаемом Astra Linux окружении.

## Следующие этапы

### P1 — provider resilience

- [ ] mocked full HTTP contract Open-Meteo;
- [ ] jittered retry и circuit breaker;
- [ ] измеримый rate limit;
- [ ] stale-cache fallback с возрастом данных;
- [ ] provider latency/error/fallback metrics;
- [ ] model-run и grid metadata через provider, который их реально отдаёт.

### P1 — научная валидация

- [ ] источники и версии `Tbase/Tupper`;
- [ ] crop/region/cultivar validation;
- [ ] региональная фенология с uncertainty;
- [ ] frost thresholds по культуре и фазе;
- [ ] surface temperature, terrain и ensemble inputs;
- [ ] сезонный ряд и правила непрерывности для ГТК;
- [ ] локальный FAO-56 только после полного набора входов.

### P1/P2 — новые данные

- [ ] SoilGrids adapter и ocean/no-data validation;
- [ ] ERA5-Land queued job/cache pipeline;
- [ ] Sentinel-2/MODIS provider с quality masks;
- [ ] provenance/version/resolution для каждого показателя.

## Критерий полевого пилота

- [x] реальные данные без синтетического fallback;
- [x] явная деградация качества;
- [x] все включённые поля мониторятся;
- [x] race-safe PostgreSQL/Redis contracts;
- [ ] clean-host deployment;
- [ ] реальный Telegram smoke;
- [ ] параллельная проверка с локальной метеостанцией;
- [ ] журнал ошибок и метрики эксплуатации;
- [ ] утверждённый регламент: бот — screening, не автономное решение.
