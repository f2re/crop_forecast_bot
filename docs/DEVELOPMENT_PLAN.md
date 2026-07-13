# План модернизации Crop Forecast Bot

Дата актуализации: **2026-07-13**.

## Текущее состояние

Основной Telegram и научный контур работает через единый aiogram-entrypoint. PostgreSQL является source of truth, Redis используется для FSM и межпроцессной координации, Open-Meteo — для оперативного прогноза и ограниченной истории, ERA5-Land — для однородного сезонного сравнения.

Текущий завершённый code-level срез: **PR #29 — version-consistent release rollback, backup restore verification и live provider gates**. Полный CI прошёл, включая реальные PostgreSQL/Redis integration tests и `pg_dump → pg_restore` с непустыми данными.

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
        ↓
versioned systemd release + heartbeat + recovery evidence
```

## Инварианты принятия изменений

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
12. Код, systemd-unit и healthcheck рассматриваются как один versioned release.
13. Failed activation не оставляет новый код или unit активными без успешного heartbeat.
14. Backup считается проверенным только после реального restore и сравнения данных/схемы.
15. Многолетнее сравнение использует одну фиксированную модель для текущего и reference-периода.
16. Сумма не сравнивается при пропуске; отношение температуры в °C к среднему не вычисляется.
17. Эмпирический процентиль не называется вероятностью, SPI/SPEI или станционной нормой.
18. Релиз принимается после static/policy checks, unit/contract, integration, migration и recovery gates.

## Завершённые вертикальные срезы

### Field-readiness — PR #21

- [x] `insufficient_forecast_data` отделён от подтверждённого `no_risk`;
- [x] ГДД строго от локальной даты начала сезона;
- [x] все enabled fields мониторятся в фоне;
- [x] local-morning digest;
- [x] race-safe onboarding;
- [x] provider provenance и regression tests.

### Telegram/FSM reliability — PR #24

- [x] production `build_dispatcher`;
- [x] Dispatcher-flow `field → crop → season → phase → report`;
- [x] RedisStorage reopen основных FSM-веток;
- [x] controlled PostgreSQL/Redis error UX;
- [x] deleted-message callback recovery;
- [x] единый каталог ручных фаз.

### Process failure orchestration — PR #25

- [x] renewable Redis job lease;
- [x] отмена provider/report после lease loss;
- [x] запрет новых side effects после потери ownership;
- [x] real Redis long-job, lock-loss и crash/TTL tests;
- [x] user/field/season mutations в одной транзакции;
- [x] real PostgreSQL failure-injection до `COMMIT`;
- [x] rollback без частичных записей.

Ограничение: Telegram `sendMessage` не поддерживает application idempotency key. Абсолютный exactly-once результат между внешней отправкой и dedup commit недоказуем.

### Накопленные осадки и атмосферная испаряемость — PR #26

- [x] накопленные осадки и provider ET₀ по завершённым локальным суткам;
- [x] `ΣP−ΣET₀` только по парным валидным суткам;
- [x] локальная граница сезона;
- [x] прогноз исключён из накоплений;
- [x] dry/wet threshold `1 мм/сут` по ETCCDI/Climdex;
- [x] текущая/максимальная сухая серия;
- [x] Rx1day/Rx5day operation с continuity guard;
- [x] показатели не называются влагозапасом или дозой полива.

Методика: `docs/SCIENTIFIC_WATER_INDICATORS.md`.

### Однородное сезонное сравнение ERA5-Land — PR #27

- [x] typed climate DTO и async provider port;
- [x] раздельные `current_daily` и `reference_daily`;
- [x] одна модель `models=era5_land` для обеих серий;
- [x] reference period 1991–2020;
- [x] cache 6 часов / 30 суток;
- [x] latency-aware фактический конец текущего ряда;
- [x] same-length windows и минимум 20 reference-лет;
- [x] empirical percentile без distribution fit;
- [x] температура, осадки, ET₀, ГДД и сухие серии;
- [x] no `Best Match`, no temperature ratio, no implicit zero;
- [x] fail-soft operational report;
- [x] Telegram limit 4096 символов.

Методика: `docs/SCIENTIFIC_CLIMATE_REFERENCE.md`.

### Release recovery и restore evidence — PR #29

- [x] unit-файлы рендерятся из точного target release;
- [x] deploy/update/rollback используют одну реализацию unit rendering;
- [x] failed activation восстанавливает предыдущие code symlink и unit-файлы;
- [x] восстановленный release повторно проходит `active + heartbeat`;
- [x] failed initial activation без previous release останавливает service и удаляет broken link;
- [x] systemd runtime paths централизованно рендерятся;
- [x] release state machine покрыт детерминированными tests;
- [x] PostgreSQL dump восстанавливается в изолированную local database;
- [x] проверяются schema fingerprint, Alembic revision и core-table fingerprints;
- [x] CI restore round trip содержит непустые user/field/season данные;
- [x] отдельные live operational и homogeneous ERA5-Land smoke contracts;
- [x] weekly/manual provider workflow с JSON artifacts;
- [x] полный CI зелёный.

## Активный вертикальный срез — внешняя полевая приёмка

Приоритет: **P0**.

Эти шаги требуют реального Linux host и Telegram token; обычный GitHub-hosted CI не является их заменой.

1. Чистая Debian 12 VM: `deploy.sh` документированной командой.
2. Проверка service, heartbeat, PostgreSQL, Redis и Alembic head.
3. Reboot и подтверждение автоматического systemd startup.
4. `verify-production.sh --live-all` на контрольной точке.
5. Telegram flow для двух полей, разных культур/сезонов/уведомлений.
6. `update.sh` на новый release.
7. Намеренно неисправный release и автоматическое восстановление старого кода/unit.
8. `verify-backup-restore.sh` последнего production dump.
9. Повторный Telegram flow после rollback.
10. Повторение на поддерживаемом Astra Linux окружении.

Definition of Done:

- deploy/update/rollback воспроизводимы только документированными командами;
- service восстанавливается после reboot;
- failed release не остаётся активным;
- backup реально восстанавливается;
- Telegram flow работает до и после rollback;
- live provider workflow имеет успешный evidence artifact;
- status/doctor отражают фактическое состояние.

## Остаточные P0 failure scenarios

- [ ] физический разрыв PostgreSQL-соединения во время `COMMIT`;
- [ ] Redis outage после получения callback lease;
- [ ] crash после принятия Telegram-сообщения и до dedup commit;
- [ ] конкурентное редактирование Telegram-сообщения;
- [ ] operator runbook для неоднозначного внешнего результата.

## Этап 0 — runtime

Статус: **code-level выполнено**.

- [x] aiogram 3.x и `python -m src.bot.main`;
- [x] Router/FSM основного пути;
- [x] graceful startup/shutdown;
- [x] systemd readiness, heartbeat и watchdog;
- [x] native deploy/update/rollback/status;
- [x] callback idempotency;
- [x] distributed renewable scheduler locks;
- [x] version-consistent code/unit rollback tests.

## Этап 1 — PostgreSQL и Redis

Статус: **production contracts + real-service CI выполнены**.

- [x] Alembic baseline и обязательный head;
- [x] `Field` и `CropSeason`;
- [x] несколько полей;
- [x] Redis FSM restart;
- [x] PostgreSQL partial unique indexes;
- [x] row locking active mutations;
- [x] multi-client Redis leases;
- [x] two-worker alert/digest tests;
- [x] race-safe onboarding;
- [x] atomic rollback test;
- [x] backup/restore round trip с data fingerprint;
- [ ] cleanup migration legacy user coordinate/crop columns после production-проверки.

## Этап 2 — научная целостность

### ГДД

- [x] crop-specific `Tbase`;
- [x] optional `Tupper`;
- [x] completed/forecast separation;
- [x] local-date season boundary;
- [x] coverage и missing fraction;
- [x] no automatic phenology;
- [ ] independent crop/region/cultivar validation;
- [ ] versioned parameter sources;
- [ ] расширенный leap-year/DST/long-gap suite.

### ГТК

- [x] completed days only;
- [x] `Tmean > 10°C`;
- [x] minimum warm-day count;
- [x] missing fraction control;
- [x] no universal classification;
- [ ] homogeneous season continuity rules;
- [ ] regional interpretation sources.

### ET₀, осадки и водный статус

- [x] provider ET₀ явно маркируется;
- [x] paired-data validation;
- [x] no irrigation-dose claim;
- [x] накопленные `P`, `ET₀`, `ΣP−ΣET₀`;
- [x] dry/wet spells и Rx1day/Rx5day;
- [x] отрицательные значения/пропуски fail-closed;
- [ ] полевая валидация по станции/лизиметру;
- [ ] local FAO-56 Penman–Monteith;
- [ ] soil/root-zone storage model;
- [ ] `Kc` только с валидированной фазой.

### Климатическая реанализная база

- [x] homogeneous ERA5-Land current/reference contract;
- [x] fixed 1991–2020 reference;
- [x] same-length season-to-date windows;
- [x] empirical percentiles и descriptive quantiles;
- [x] provenance, cache policy и latency marker;
- [x] leap-day/cross-year tests;
- [x] live smoke contract и scheduled workflow;
- [ ] первый успешный live artifact;
- [ ] региональная bias-оценка по станциям;
- [ ] прямой CDS job/object-cache pipeline;
- [ ] SPI/SPEI после отдельной валидации distribution fit.

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

- [x] typed weather/climate ports/DTO;
- [x] timeout, retry, cache и bounded concurrency;
- [x] controlled fallback;
- [x] resource shutdown;
- [x] retrieval/cache provenance;
- [x] mocked и live-smoke contracts;
- [ ] jittered retry и circuit breaker;
- [ ] measurable rate limiter;
- [ ] stale-cache age/quality marker;
- [ ] provider metrics.

## Этап 4 — UX и lifecycle данных

- [x] полный Dispatcher test;
- [x] restart основных FSM-веток;
- [x] fail-closed dependency error UX;
- [ ] синхронизировать `/help` о назначении даты сезона;
- [ ] field archive/delete flow;
- [ ] user data export/delete;
- [ ] quiet hours и configurable delivery window;
- [ ] administrative provider status.

## Этап 5 — новые данные

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

- [x] Bash/systemd versioned releases;
- [x] PostgreSQL backup перед update;
- [x] version-consistent code/unit rollback;
- [x] automated failed-start rollback state-machine tests;
- [x] real backup/restore verification;
- [x] operational + climate live smoke commands;
- [x] scheduled provider evidence workflow;
- [x] real PostgreSQL/Redis CI без Docker;
- [ ] clean-host Debian 12 test;
- [ ] Astra Linux test;
- [ ] periodic restore verification на production backup;
- [ ] JSON logs и correlation ID во всех слоях;
- [ ] provider/scheduler/Telegram metrics;
- [ ] signed release source policy.

## Definition of Done полевого пилота

- [x] field-readiness и Telegram/FSM reliability;
- [x] scheduler heartbeat/loss и transaction rollback;
- [x] научные накопления с provenance/QC;
- [x] homogeneous ERA5-Land reference с QC;
- [x] release rollback state machine;
- [x] PostgreSQL restore round trip в CI;
- [ ] clean-host deploy/reboot/update/rollback;
- [ ] реальный Telegram smoke для двух полей;
- [ ] успешный live provider artifact;
- [ ] параллельное сравнение с локальной станцией;
- [ ] screening-only регламент и независимый резервный канал критичных предупреждений.
