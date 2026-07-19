# План модернизации Crop Forecast Bot

Дата актуализации: **2026-07-19**.

## Цель ближайшего релиза

Перевести code-level пилот в контролируемый полевой пилот: подтвердить deployment/Telegram-flow во внешней среде и начать накапливать фактические наблюдения пользователя для проверки прогнозов и будущих расчётов.

Бот не подменяет официальные предупреждения, локальную метеостанцию, агрономическое обследование или нормативную инструкцию к препарату.

## Подтверждённое состояние

- один aiogram 3.x entrypoint;
- PostgreSQL + SQLAlchemy 2 async + Alembic;
- Redis FSM, callback idempotency, renewable leases и deduplication;
- несколько полей, культура, дата сезона и ручная фаза;
- Open-Meteo Forecast Best Match/Historical Weather;
- homogeneous ERA5 current/reference, база 1991–2020;
- общий climate prefix, полный по `Tmean/P/ET₀`;
- GDD, сезонный ГТК, provider ET₀, `P−ET₀`, накопления и precipitation extremes;
- GFS Ensemble multi-hazard screening;
- ручной обзор `/risks`;
- risk history и trend `/history`;
- delivery modes, quiet hours и compact digest;
- versioned systemd release, heartbeat, rollback и backup/restore;
- unit/contract, PostgreSQL/Redis integration и live provider gates.

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
10. Background monitoring охватывает все enabled fields.
11. Side effects прекращаются после потери scheduler lease.
12. Accepted risk run сохраняется до delivery decision и Telegram side effect.
13. Quiet hours влияют на delivery, но не на scientific result/history.
14. State-changing callback задаёт конечное состояние, а не toggle.
15. Код, systemd units, migrations и healthcheck образуют один release.
16. Функция готова только после Telegram-flow и тестов.

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

Schema:

```text
risk_delivery_mode: immediate | digest | high_only
quiet_hours_start: local hour | null
quiet_hours_end: local hour | null
```

Поведение:

- один compact multi-hazard message на поле;
- `immediate` — state-based delivery;
- `digest` — один обычный message на local date;
- `high_only` — только `level=high`;
- watch/elevated откладываются в quiet hours;
- high risk bypasses quiet hours/daily digest;
- accepted run сохраняется независимо от delivery;
- DST/cross-midnight tests;
- Alembic head `20260719_0005`.

### Provider contract hardening — PR #43

- generic Forecast больше не отправляет устаревший `models=auto`;
- operational metadata показывает `best_match`;
- climate current/reference переведены на одну fixed ERA5 configuration;
- current climate period complete по `Tmean/P/ET₀`;
- live provider gates и pytest artifacts.

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
- add observation через короткий FSM;
- delete только собственной записи;
- локальное время поля;
- единицы и допустимые диапазоны;
- `/journal` optional command;
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
2. update и intentionally failed release → verified rollback;
3. real Telegram smoke: два пользователя, несколько полей/timezone;
4. Astra Linux smoke;
5. message/log/heartbeat evidence;
6. operator runbook для `sending`;
7. screening-only регламент;
8. независимый официальный warning channel.

## P1 — после полевого журнала

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

### Provider observability

- latency/error/cache/fallback metrics;
- stale-cache age;
- simple circuit breaker;
- admin provider status;
- bounded field concurrency только после метрик.

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
- не переписывать sync provider clients до появления метрик;
- не вводить queues/microservices/CQRS без подтверждённой нагрузки.

## Definition of Done следующего релиза

- полевой журнал доступен из production Router graph;
- данные field-scoped и restart-safe;
- full CI/live gates зелёные;
- clean-host/Telegram acceptance выполнены или остаются явно blocking;
- journal observations не подменяют provider data;
- audit/capability/status/docs синхронизированы.

Глубокий аудит: `docs/DEEP_AUDIT_2026-07-19.md`.
