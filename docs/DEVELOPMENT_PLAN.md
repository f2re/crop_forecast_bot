# План модернизации Crop Forecast Bot

Дата актуализации: **2026-07-12**.

## Текущее состояние

Основной научный и runtime-контур работает через единый aiogram-entrypoint. PostgreSQL является source of truth, Redis используется для FSM и координации, Open-Meteo — для оперативного прогноза и ограниченной истории, ERA5-Land — для однородного сезонного сравнения.

Последний завершённый вертикальный срез: **ERA5-Land seasonal reference, слит через PR #27**.

## Целевая архитектура

```text
Telegram / aiogram Router + Redis FSM
        ↓
application services / typed ports
        ↓
domain / scientifically bounded calculations
        ↓
infrastructure adapters
  ├─ Open-Meteo forecast / bounded season history
  ├─ ERA5-Land current season + 1991–2020 reference
  ├─ PostgreSQL repositories / Alembic
  ├─ Redis callback/job leases / deduplication
  └─ optional source-attributed RAG
```

## Правила принятия изменений

1. Один Telegram framework и один entrypoint.
2. Handlers не выполняют расчёты, HTTP и блокирующий I/O.
3. PostgreSQL — source of truth; Redis — FSM и coordination.
4. Observation, reanalysis, forecast и reference period не смешиваются.
5. Отсутствие данных не заменяется эвристикой, интерполяцией или нулём без отдельного валидированного метода.
6. Формула имеет источник, единицы, период, допустимый диапазон и тесты.
7. Неподдерживаемая функция явно выключена.
8. State-changing callback задаёт конечное состояние, а не toggle.
9. Background monitoring относится ко всем enabled fields.
10. Пользовательская state-changing операция не имеет промежуточных commit.
11. Worker не продолжает side effects после потери lease ownership.
12. Релиз принимается после CI, migration check и runtime smoke.
13. Production разворачивается Bash/systemd без Docker.
14. Накопления строятся только по завершённым локальным суткам и сохраняют provenance.
15. Разность величин вычисляется по одному набору парных наблюдений.
16. Многолетнее сравнение использует одну фиксированную модель для текущего и reference-периода.
17. Сумма не сравнивается при пропуске; отношение температуры в °C к среднему не вычисляется.
18. Эмпирический процентиль не называется вероятностью, SPI/SPEI или станционной нормой.

## Завершённые вертикальные срезы

### Runtime и field-readiness — PR #21

- [x] `insufficient_forecast_data` отделён от подтверждённого `no_risk`;
- [x] ГДД фильтруются строго от локальной даты начала сезона;
- [x] все enabled fields мониторятся в фоне;
- [x] daily digest использует локальное утреннее окно поля;
- [x] race-safe onboarding через upsert и row lock;
- [x] provider provenance и regression tests.

### Telegram/FSM reliability — PR #24

- [x] testable production `build_dispatcher`;
- [x] Dispatcher-flow `field → crop → season → phase → report`;
- [x] RedisStorage reopen для основных FSM-веток;
- [x] controlled PostgreSQL/Redis error UX;
- [x] deleted-message callback recovery;
- [x] единый каталог ручных фаз;
- [x] UX all-field monitoring синхронизирован с scheduler.

### Process failure orchestration — PR #25

- [x] reusable `RenewingLease` с token-checked heartbeat;
- [x] продление scheduler lock во время долгого provider/report I/O;
- [x] отмена текущего read/report после потери ownership;
- [x] запрет перехода к следующему полю после lease loss;
- [x] real Redis tests для long job, forced lock loss и crash/TTL recovery;
- [x] `_lock_user` без промежуточного commit;
- [x] crop/season/phase mutations под user row lock;
- [x] real PostgreSQL failure-injection после `flush` и до `COMMIT`;
- [x] rollback без частичных user/field/season записей;
- [x] caller cancellation не оставляет защищённую coroutine в фоне.

Ограничение: Telegram `sendMessage` не поддерживает application idempotency key. Абсолютный exactly-once результат между внешней отправкой и фиксацией dedup недоказуем.

### Накопленные осадки и атмосферная испаряемость — PR #26

- [x] накопленные осадки по завершённым локальным суткам;
- [x] накопленная provider ET₀ с независимым QC;
- [x] `ΣP−ΣET₀` только по парным валидным суткам;
- [x] локальная граница сезона;
- [x] прогноз исключён из накоплений;
- [x] отрицательные значения не превращаются в ноль;
- [x] dry/wet threshold `1 мм/сут` по ETCCDI/Climdex;
- [x] текущая и максимальная сухая серия только на непрерывном ряду;
- [x] максимум осадков за 1 и 5 последовательных суток;
- [x] показатели не называются влагозапасом, фактической ET культуры или дозой полива.

Методика: `docs/SCIENTIFIC_WATER_INDICATORS.md`.

### Однородное сезонное сравнение ERA5-Land — PR #27

- [x] typed climate DTO и async provider port;
- [x] раздельные `current_daily` и `reference_daily`;
- [x] одна модель `models=era5_land` для обеих серий;
- [x] reference period 1991–2020;
- [x] текущий ряд cache 6 часов, reference cache 30 суток;
- [x] полностью пустой хвост задержанного ERA5-Land удаляется без подмены прогнозом;
- [x] фактическая дата окончания ряда показывается пользователю;
- [x] same-length windows с одинаковой календарной датой старта;
- [x] минимум 20 валидных референсных лет;
- [x] empirical mid-rank percentile без distribution fit;
- [x] средняя температура, осадки, provider ET₀, ГДД и сухие серии;
- [x] накопленные метрики требуют полного ряда;
- [x] отношение температуры в °C к среднему запрещено;
- [x] 29 февраля не сдвигается эвристически;
- [x] отказ climate provider не блокирует оперативный отчёт;
- [x] Telegram-текст укладывается в 4096 символов;
- [x] SPI/SPEI, station normal и вероятность не заявляются;
- [x] полный CI: static/policy, unit/contract, PostgreSQL/Redis integration, Alembic graph.

Методика: `docs/SCIENTIFIC_CLIMATE_REFERENCE.md`.

## Активный вертикальный срез — clean-host release gate

Приоритет: **P0**.

1. Чистая Debian 12 VM: `deploy.sh` без ручной правки кода.
2. Reboot и подтверждение автоматического systemd startup.
3. Реальный Telegram smoke для двух полей.
4. `update.sh` на новый release.
5. Намеренно повреждённый release и healthcheck failure.
6. Автоматический возврат предыдущего кода и systemd unit.
7. `pg_restore` последнего dump в отдельную test database.
8. Сравнение пользователей, полей, сезонов и Alembic revision.
9. Live smoke Forecast/Historical/ERA5-Land на контрольных точках.
10. Повторение smoke на поддерживаемом Astra Linux окружении.

Definition of Done:

- deploy/update/rollback воспроизводимы только документированными командами;
- service восстанавливается после reboot;
- failed release не остаётся активным;
- backup реально восстанавливается;
- Telegram flow работает до и после rollback;
- status/doctor отражают фактическое состояние.

## Остаточные P0 failure scenarios

- [ ] физический разрыв PostgreSQL-соединения во время `COMMIT`;
- [ ] Redis outage после получения callback lease;
- [ ] crash после принятия Telegram-сообщения и до dedup commit;
- [ ] конкурентное редактирование Telegram-сообщения;
- [ ] operator runbook для неоднозначного внешнего результата.

## Этап 0 — runtime

Статус: **выполнено**.

- [x] aiogram 3.x и `python -m src.bot.main`;
- [x] Router/FSM основного пути;
- [x] graceful startup/shutdown;
- [x] systemd readiness, heartbeat и watchdog;
- [x] native deploy/update/rollback/status;
- [x] callback idempotency;
- [x] distributed renewable scheduler locks.

## Этап 1 — PostgreSQL и Redis

Статус: **production + real-service integration выполнены**.

- [x] Alembic baseline и обязательный head;
- [x] adoption legacy schema;
- [x] `Field` и `CropSeason`;
- [x] несколько полей;
- [x] Redis FSM restart;
- [x] PostgreSQL partial unique indexes;
- [x] row locking active field/user mutations;
- [x] multi-client Redis leases;
- [x] two-worker alert/digest tests;
- [x] race-safe onboarding;
- [x] atomic pre-commit rollback test;
- [x] crash/TTL lease recovery test;
- [ ] cleanup migration legacy user coordinate/crop columns после production-проверки.

## Этап 2 — научная целостность

### ГДД

- [x] crop-specific `Tbase` из одного каталога;
- [x] optional `Tupper` только при явной настройке;
- [x] completed/forecast separation;
- [x] local-date season boundary;
- [x] coverage и missing fraction;
- [x] no automatic phenology;
- [ ] independent crop/region/cultivar validation;
- [ ] versioned parameter sources;
- [ ] leap year, DST и long-gap suite.

### ГТК

- [x] completed days only;
- [x] `Tmean > 10°C`;
- [x] minimum warm-day count;
- [x] missing fraction control;
- [x] no universal classification;
- [ ] season-consistent homogeneous series;
- [ ] vegetation-period continuity rules;
- [ ] regional interpretation sources.

### ET₀, осадки и водный статус

- [x] ET₀ обозначен как provider variable;
- [x] paired-data validation;
- [x] no irrigation-dose claim;
- [x] накопленные `P` и provider `ET₀`;
- [x] сезонная `ΣP−ΣET₀` по парным суткам;
- [x] dry/wet threshold и bounded-period spell metrics;
- [x] Rx1day/Rx5day с continuity guard;
- [x] отрицательные значения и пропуски fail-closed;
- [ ] полевая валидация по станции/лизиметру;
- [ ] local FAO-56 Penman–Monteith;
- [ ] soil/root-zone storage model;
- [ ] Kc только с валидированной фазой.

### Климатическая реанализная база

- [x] homogeneous ERA5-Land current/reference contract;
- [x] fixed 1991–2020 reference;
- [x] same-length season-to-date windows;
- [x] empirical percentiles и descriptive quantiles;
- [x] provenance, cache policy и latency marker;
- [x] leap-day/cross-year tests;
- [x] no `Best Match`, no temperature ratio, no implicit zero;
- [ ] live full-period контрольные точки;
- [ ] региональная bias-оценка по станциям;
- [ ] прямой CDS job/object-cache pipeline;
- [ ] SPI/SPEI после отдельной валидации distribution fit и временных масштабов.

### Заморозки

- [x] forecast rows only;
- [x] air 2 m vs plant/surface distinction;
- [x] explicit insufficient-data state;
- [x] fail-closed unavailable-data notification;
- [x] no fake probability or exact event hour;
- [ ] normative crop/phase damage thresholds;
- [ ] surface temperature provider;
- [ ] terrain/cold-air drainage correction;
- [ ] ensemble uncertainty;
- [ ] POD/FAR/CSI validation dataset.

## Этап 3 — provider resilience

Приоритет: **P1**.

- [x] typed weather and climate ports/DTO;
- [x] timeout, retry, cache и bounded concurrency;
- [x] controlled historical/climate fallback;
- [x] provider resource shutdown;
- [x] retrieval/cache provenance;
- [x] mocked ERA5-Land request contract;
- [ ] mocked full operational HTTP contract;
- [ ] jittered retry и circuit breaker;
- [ ] measurable rate limiter;
- [ ] stale-cache age/quality marker;
- [ ] provider metrics;
- [ ] actual model-run/grid metadata from supporting endpoints.

## Этап 4 — UX и lifecycle данных

- [x] полный Dispatcher test;
- [x] restart основных FSM-веток;
- [x] fail-closed dependency error UX;
- [ ] синхронизировать одну строку `/help`: дата сезона также нужна для водных накоплений и ERA5-Land;
- [ ] field archive/delete flow;
- [ ] user data export/delete;
- [ ] quiet hours и configurable delivery window;
- [ ] administrative provider status.

## Этап 5 — новые данные

Приоритет: **P1/P2**.

- [ ] SoilGrids DTO/adapter и ocean/no-data validation;
- [ ] direct CDS/ERA5-Land asynchronous job/object-cache pipeline;
- [ ] Sentinel-2/MODIS provider с quality masks;
- [ ] provenance/version/resolution для каждого показателя;
- [ ] ни одна функция не появляется в UI до тестируемого vertical slice.

## Этап 6 — RAG

- [x] optional dependency profile;
- [x] lazy initialization;
- [x] feature flag и source display;
- [x] fail-closed response;
- [ ] document version/date/category metadata;
- [ ] citation-to-chunk validation;
- [ ] prompt-injection tests;
- [ ] Russian agronomy evaluation set;
- [ ] hard guard для доз/препаратов.

## Этап 7 — release engineering и наблюдаемость

- [x] Bash/systemd releases;
- [x] PostgreSQL backup перед update;
- [x] atomic activation и code rollback;
- [x] verification script и live operational provider smoke command;
- [x] real PostgreSQL/Redis CI без Docker;
- [ ] `uv.lock` на целевых ОС;
- [ ] clean-host Debian 12 test;
- [ ] Astra Linux test;
- [ ] automated failed-start rollback test;
- [ ] periodic restore verification;
- [ ] JSON logs и correlation ID во всех слоях;
- [ ] provider/scheduler/Telegram metrics;
- [ ] signed release source policy.

## Definition of Done полевого пилота

- [x] field-readiness и Telegram/FSM reliability слиты с зелёным CI;
- [x] scheduler heartbeat/loss и transaction rollback проверены реальными сервисами;
- [x] накопленные показатели осадков/ET₀ имеют источники, единицы, QC и Telegram tests;
- [x] homogeneous ERA5-Land reference имеет фиксированный период, provenance, QC и Telegram tests;
- [ ] clean-host deploy/update/rollback пройден;
- [ ] реальный Telegram smoke для двух полей пройден;
- [ ] Open-Meteo/ERA5-Land live smoke пройден на контрольных точках;
- [ ] параллельное сравнение с локальной станцией выполнено;
- [ ] регламент эксплуатации утверждает screening-only статус;
- [ ] критичные предупреждения имеют независимый резервный канал.
