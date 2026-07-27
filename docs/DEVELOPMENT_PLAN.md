# План модернизации Crop Forecast Bot

Дата актуализации: **2026-07-27**.

## Цель ближайшего релиза

Перевести проверенный code-level MVP в контролируемый полевой пилот на слабом сервере:

1. подтвердить чистую установку, reboot и автоматическое green-main update;
2. подтвердить реальный Telegram-flow нескольких пользователей и полей;
3. начать накапливать фактические наблюдения пользователя;
4. не увеличивать runtime и dependency surface без измеримой пользы.

Бот не подменяет официальные предупреждения, локальную метеостанцию, агрономическое обследование или нормативную инструкцию к препарату.

## Подтверждённое состояние

- один aiogram 3.x entrypoint;
- PostgreSQL + SQLAlchemy 2 async + Alembic;
- Redis FSM, callback idempotency, renewable leases и deduplication;
- несколько полей, культура, дата сезона и ручная фаза;
- Open-Meteo Forecast Best Match/Historical Weather;
- GDD, сезонный ГТК, provider ET₀, `P−ET₀`, накопления и precipitation extremes;
- GFS Ensemble multi-hazard screening;
- ручной обзор `/risks`;
- risk history и trend `/history`;
- delivery modes, quiet hours и compact digest;
- versioned systemd release, heartbeat, rollback и backup/restore;
- unit/contract, PostgreSQL/Redis integration и live provider gates;
- low-resource production profile;
- pull-based green-main CD.

Опциональные ERA5 1991–2020 и RAG сохранены, но выключены в production MVP.

## Архитектурные инварианты

1. Один Telegram framework и один entrypoint.
2. Handlers не выполняют формулы, HTTP и блокирующий I/O.
3. Все внешние I/O-контракты асинхронные и типизированные.
4. PostgreSQL — source of truth; Redis — FSM и coordination.
5. Observation, reanalysis, forecast и climate reference не смешиваются.
6. Пропуск не превращается в ноль, безопасность или synthetic fallback.
7. Формула имеет источник, единицы, период, область применимости и тесты.
8. `k/n` не называется calibrated probability.
9. CAPE не называется прогнозом грозы или града.
10. Background monitoring охватывает все явно enabled fields.
11. Side effects прекращаются после потери scheduler lease.
12. Accepted risk run сохраняется до delivery decision и Telegram side effect.
13. Quiet hours влияют на delivery, но не на scientific result/history.
14. State-changing callback задаёт конечное состояние, а не toggle.
15. Код, systemd units, migrations и healthcheck образуют один release.
16. Systemd readiness требует реального Telegram `getMe`.
17. Автообновление `main` выполняется только после green CI точного SHA.
18. Функция готова только после Telegram-flow и тестов.

## Завершённые вертикальные срезы

### Ручной обзор риска — PR #39

- кнопка и `/risks`;
- общий domain calculation;
- `k/n`, P10/P50/P90, lead time и provenance;
- fail-closed UX.

### Журнал и тренд — PR #41

- `risk_forecast_runs/signals`;
- atomic accepted run + signals;
- delivery states;
- `new / strengthening / stable / weakening / cleared`;
- retention;
- `/history`.

### Quiet hours и risk digest — PR #43

- `immediate / digest / high_only`;
- local quiet hours;
- один multi-hazard message;
- high-risk bypass;
- accepted run независимо от delivery;
- Alembic head `20260719_0005`.

### Низкоресурсный MVP и green-main CD — PR #44

#### Запуск

- реальный Telegram `getMe` до `READY=1`;
- `python -m src.bot.main --startup-smoke` для CI;
- bounded `asyncio.to_thread` executor;
- RAG Router не импортируется при disabled feature;
- первый risk cycle всех сохранённых полей после здорового старта.

#### Автоматическое обновление

```text
git ls-remote
→ exact SHA GitHub Actions gate
→ shallow clone
→ SHA race check
→ shared virtualenv
→ backup
→ migrate
→ preflight
→ activate
→ Telegram/heartbeat healthcheck
→ rollback
```

- timer каждые 15 минут;
- pending/failed/unavailable CI не изменяет active release;
- virtualenv переиспользуется до изменения Python minor/requirements;
- сохраняются два release и три backup.

#### Ресурсы

- базовый installer без GDAL, compiler toolchain и RAG dependencies;
- два blocking I/O workers;
- один BLAS/OpenMP thread;
- soft systemd memory/CPU/IO controls;
- climate comparison и RAG выключены по умолчанию;
- risk-history retention 30 суток.

#### Автоматические проверки

- production startup-smoke;
- green-CI release gate;
- saved multi-field scheduler cycle;
- disabled optional modules;
- minimal packages и systemd resource contracts;
- полный прежний CI/integration/live-provider набор.

## Активный следующий кодовый срез — полевой журнал

### Причина

Новые модельные индексы без фактических наблюдений дают ограниченную добавочную ценность. Полевой журнал создаёт контекст для рекомендаций, station validation, water balance и оценки полезности alerts.

### Минимальная схема

```text
field_observations
- id
- field_id
- observed_at
- observation_type
- numeric_value nullable
- unit nullable
- note nullable
- source
- created_at
```

Первый набор `observation_type`:

```text
phase
operation
irrigation
rain_gauge
station_tmin
station_tmax
damage
note
```

### Telegram UX

- кнопка **«Журнал поля»**;
- список последних записей;
- добавление через короткий FSM;
- удаление только собственной записи;
- локальное время поля;
- единицы и допустимые диапазоны;
- `/journal` как дополнительная команда;
- без автоматической интерпретации повреждения.

### Инварианты

- запись принадлежит конкретному field;
- observation time timezone-aware на входе и хранится UTC;
- user source маркируется явно;
- irrigation/rain values не смешиваются с model precipitation;
- station temperature не заменяет provider series автоматически;
- photo/file reference optional и не анализируется в первом срезе;
- no free-form pesticide/fertilizer dosing logic.

### Тесты

- Alembic fresh/upgrade/downgrade;
- ownership и cascade delete;
- value/unit validation;
- timezone/DST;
- restart-safe FSM;
- duplicate callback protection;
- Telegram add/list/delete scenario;
- PostgreSQL integration;
- message length.

## P0 — внешняя приёмка

1. clean Debian 12 deploy → migrate → start → reboot;
2. проверить `main` update после green CI;
3. intentionally failed release → verified rollback;
4. real Telegram smoke: два пользователя, несколько полей/timezone;
5. подтвердить startup calculation сохранённых fields;
6. Astra Linux smoke;
7. message/log/heartbeat/timer evidence;
8. operator runbook для `sending`;
9. screening-only регламент;
10. независимый официальный warning channel.

## P1 — после полевого журнала

### Provider observability

- latency/error/cache/fallback metrics;
- stale-cache age;
- simple circuit breaker;
- admin provider status;
- bounded field concurrency только после метрик.

### Окно полевых работ

- операция выбирается явно;
- осадки, ветер/порывы, температура, RH/VPD и previous rain;
- explanation per constraint;
- отдельное spray weather window без обхода label;
- no opaque suitability score.

### Official warnings

- CAP adapters по стране/региону;
- issuer/identifier/effective/expires/area/severity;
- отдельные секции `официальное предупреждение` и `модельный сигнал`;
- no probability mixing.

### Station verification

- station observation import;
- forecast run ↔ observation matching;
- bias/MAE/RMSE;
- POD/FAR/CSI;
- below-threshold daily evaluations;
- Brier/reliability по risk/lead/season/region.

## P2

1. field polygon geometry;
2. SoilGrids context с uncertainty;
3. Sentinel-2 L2A + SCL/cloud masks;
4. own-field temporal baseline;
5. local FAO-56 при полном наборе входов;
6. validated `Kc/Ks` и root-zone balance;
7. GloFAS/flood screening;
8. pathogen-specific disease models;
9. отдельный hail validation track.

## Технический долг

- вынести weather-risk cycle из `scheduler.py` в application service;
- разделить `handlers/core.py` на feature routers;
- привести optional RAG к application service/bounded executor/timeouts;
- переименовать `frost_alerts_enabled` в `weather_risk_alerts_enabled`;
- удалить transitional `users` columns после production upgrade evidence;
- постепенно включить mypy и Bandit;
- добавить измерение памяти/latency на целевом слабом сервере;
- не вводить queues/microservices/CQRS без подтверждённой нагрузки.

## Definition of Done следующего релиза

- clean-host MVP и auto-update подтверждены на целевом server;
- полевой журнал доступен из production Router graph;
- данные field-scoped и restart-safe;
- full CI/live gates зелёные;
- journal observations не подменяют provider data;
- audit/capability/status/docs синхронизированы.

Эксплуатация MVP: `docs/LOW_RESOURCE_MVP.md`.  
Глубокий аудит: `docs/DEEP_AUDIT_2026-07-19.md`.
