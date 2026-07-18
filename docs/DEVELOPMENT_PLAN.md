# План модернизации Crop Forecast Bot

Дата актуализации: **2026-07-18**.

## Цель ближайшего релиза

Довести code-level пилот до воспроизводимого контролируемого полевого пилота: подтвердить установку и Telegram-flow во внешней среде, снизить шум предупреждений и начать региональную проверку прогнозов.

Бот не подменяет официальные предупреждения, локальную метеостанцию, агрономическое обследование или нормативную инструкцию к препарату.

## Подтверждённое состояние `main`

- один aiogram 3.x entrypoint;
- PostgreSQL + SQLAlchemy 2 async + Alembic;
- Redis FSM, callback idempotency, renewable leases и deduplication;
- несколько полей, культура, дата сезона и ручная фаза;
- Open-Meteo Forecast/Historical Weather;
- homogeneous ERA5-Land current/reference, база 1991–2020;
- GDD, сезонный ГТК, provider ET₀, `P−ET₀`, накопления и precipitation extremes;
- GFS Ensemble multi-hazard screening;
- ручной обзор рисков `/risks`;
- persistent risk history и тренд `/history`;
- versioned systemd release, heartbeat, rollback и backup/restore verification;
- unit/contract, PostgreSQL/Redis integration и live provider gates.

## Архитектурные инварианты

1. Один Telegram framework и один entrypoint.
2. Handlers не выполняют формулы, HTTP и блокирующий I/O.
3. Все внешние I/O-контракты асинхронные и типизированные.
4. PostgreSQL — source of truth; Redis — FSM и coordination.
5. Observation, reanalysis, forecast и climate reference не смешиваются.
6. Пропуск не превращается в ноль, безопасность или синтетический fallback.
7. Формула имеет источник, единицы, период, область применимости и тесты.
8. `k/n` не называется откалиброванной вероятностью.
9. CAPE не называется прогнозом грозы или града.
10. Background monitoring охватывает все явно enabled fields.
11. Side effects прекращаются после потери scheduler lease.
12. Accepted risk run сохраняется до Telegram side effect.
13. State-changing callback задаёт конечное состояние, а не toggle.
14. Код, systemd units, миграции и healthcheck образуют один release.
15. Функция считается готовой только после Telegram-flow и тестов.

## Завершённый срез — ручной обзор рисков

PR #39:

- кнопка и `/risks`;
- application service поверх общего `RiskForecastProvider`;
- тот же `calc_ensemble_risks`, что в scheduler;
- до пяти событий, `k/n`, P10/P50/P90, lead time и provenance;
- fail-closed UX;
- Dispatcher scenario.

## Завершённый срез — журнал и тренд риска

PR #41:

### Хранение

```text
risk_forecast_runs
- field_id, source, model, retrieved_at
- analysis_date, timezone
- member_count, forecast_days
- valid_days, incomplete_days, status

risk_forecast_signals
- run_id, risk_type, event_date, lead_days, level
- members_exceeding, valid_members, member_fraction
- severe_member_fraction
- threshold, severe_threshold, unit
- p10, median, p90
- delivery_state, notified_at
```

### Гарантии

- уникальность run: `field_id + model + retrieved_at`;
- accepted run и signals сохраняются одной транзакцией;
- provider failure и incomplete ensemble не создают успешный run;
- Telegram send начинается только после commit;
- `sending` сохраняет неоднозначный внешний outcome;
- retention управляется `RISK_HISTORY_RETENTION_DAYS`;
- удаление field каскадно удаляет history.

### Тренд

Для одинаковых `field + model + risk_type + event_date` сравниваются два последних запуска:

- `new`;
- `strengthening`;
- `stable`;
- `weakening`;
- `cleared`.

Изменение уровня имеет приоритет; внутри уровня существенным считается изменение доли на 10 процентных пунктов. Тренд не является вероятностной калибровкой.

### Проверки

- Alembic head `20260718_0004`;
- idempotent run insert;
- delivery state;
- trend boundary tests;
- retention;
- scheduler persistence ordering;
- Telegram history flow;
- PostgreSQL/Redis integration;
- backup/restore;
- live GFS contract.

## Активный следующий срез — quiet hours и risk digest

### Причина

Текущий scheduler может отправить до пяти отдельных сообщений на поле за цикл. Для фермеров с несколькими полями это создаёт шум, особенно ночью и при повторных изменениях прогноза.

### Минимальный scope

На уровне `fields` добавить:

```text
risk_delivery_mode: immediate | digest | high_only
quiet_hours_start: local time | null
quiet_hours_end: local time | null
```

Не создавать отдельный rules engine.

### Поведение

- `immediate`: текущая доставка;
- `digest`: одно сообщение с событиями цикла;
- `high_only`: немедленно только `high`, остальные — в digest;
- quiet hours определяются в timezone поля;
- просроченный event после quiet hours не отправляется;
- `cleared` и strengthening можно включать в digest без отдельного спама;
- delivery state сохраняется для итогового сообщения.

### Тесты

- IANA timezone и DST;
- interval через полночь;
- несколько полей в разных timezone;
- один digest при двух workers;
- retry после Telegram failure;
- отсутствие просроченного alert;
- message length;
- restart между расчётом и delivery.

## P0 — внешняя приёмка

1. clean Debian 12 deploy → migrate → start → reboot;
2. update и intentionally failed release → verified rollback;
3. real Telegram smoke: два пользователя, несколько полей, разные timezone;
4. Astra Linux smoke;
5. сохранение message/log/heartbeat evidence;
6. operator runbook для состояния `sending`;
7. screening-only регламент и резервный канал критических предупреждений.

## P1 — наблюдаемость и отказоустойчивость

- provider latency/error/cache/fallback metrics;
- stale-cache age в metadata и Telegram UX;
- измеримый rate limiter;
- простой circuit breaker на provider adapter;
- административный provider status;
- pytest failure artifacts;
- постепенно включить mypy для domain/ports/DTO;
- включить bandit с документированными исключениями.

## P1 — станционная проверка

- импорт station observations;
- forecast run ↔ observation matching;
- bias/MAE/RMSE для непрерывных величин;
- POD/FAR/CSI для событий;
- Brier/reliability для всех daily evaluations, включая below-threshold;
- calibration по risk/lead/season/region.

Важно: текущие `risk_forecast_signals` содержат threshold crossings и достаточны для UX trend, но не являются unbiased calibration dataset.

## P1/P2 — продуктовые функции

1. окно полевых работ;
2. метеоокно опрыскивания без обхода этикетки;
3. SoilGrids + terrain screening;
4. локальная FAO-56 при полном наборе входов;
5. validated `Kc/Ks` и root-zone balance;
6. Sentinel-2/MODIS NDVI/LAI с quality masks;
7. привязка локальной метеостанции и bias correction;
8. GloFAS/flood/erosion screening.

## Технический долг

- разделить `scheduler.py`, вынеся только weather-risk cycle в application service;
- разделить `handlers/core.py` на field/season/report routers;
- переименовать `frost_alerts_enabled` в `weather_risk_alerts_enabled` совместимой миграцией;
- удалить transitional columns из `users` после production upgrade evidence;
- не переписывать sync provider clients до появления метрик;
- не вводить queues/microservices/CQRS без подтверждённой нагрузки.

## Definition of Done следующего релиза

- quiet hours/digest доступны из Telegram settings;
- нет повторного или просроченного alert;
- full CI и live provider gates зелёные;
- clean-host и real Telegram acceptance выполнены либо явно остаются blocking gate;
- технический аудит и capability matrix синхронизированы;
- новые тексты не создают claims вероятности ущерба, града или точной дозы мероприятий.

Технический аудит: `docs/TECHNICAL_AUDIT_2026-07-18.md`.
