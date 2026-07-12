# Changelog

Все существенные изменения фиксируются здесь. Проект пока не использует стабильную SemVer-линейку.

## 2026-07-12 — ERA5-Land season reference and empirical anomalies

### Added

- typed climate reference DTO and asynchronous provider port;
- fixed `era5_land` adapter for the 1991–2020 reference period through Open-Meteo;
- 30-day climate cache, bounded shared concurrency and exact coverage validation;
- same-length season-to-date windows anchored to the same local month/day;
- empirical mean, median, P10/P25/P75/P90 and mid-rank percentile summaries;
- reference comparisons for mean temperature, precipitation, provider ET₀, crop-specific GDD, dry days and maximum dry spell;
- Telegram report section with period, valid-year count, nominal grid resolution, provenance and limitations;
- `docs/SCIENTIFIC_CLIMATE_REFERENCE.md`;
- unit, provider-contract, fallback and Telegram message-length tests.

### Scientific guards

- the default mixed Open-Meteo `Best Match` model is not used for the multi-decadal reference;
- forecast rows are excluded before local-date de-duplication;
- accumulated precipitation, ET₀ and GDD are withheld if any daily value is missing;
- Celsius values use additive anomalies only; a percent-of-mean temperature is not calculated;
- 29 February is not silently shifted to another date;
- at least 20 valid historical windows are required;
- empirical percentile is not presented as probability, station climatological normal, SPI or SPEI;
- climate-provider failure degrades only the climate section and does not block the operational report.

### Known limitations

- ERA5-Land is a gridded reanalysis, not a field station;
- regional/seasonal bias has not yet been validated against local stations;
- direct CDS job/object-cache infrastructure is not implemented;
- live full-period control-point smoke remains part of the release gate.

## 2026-07-12 — accumulated precipitation and reference ET₀

### Added

- completed-period and seasonal accumulated precipitation;
- accumulated provider reference ET₀ with independent completeness checks;
- paired-day `ΣP−ΣET₀` and `ΣET₀−ΣP` climatic differences;
- dry/wet day counts with the ETCCDI/Climdex 1 mm threshold;
- trailing and maximum dry/wet spells on a continuous daily series;
- maximum 1-day and 5-consecutive-day precipitation within the selected period;
- regression tests for forecast exclusion, missing/negative values, local season boundaries and overlapping local dates;
- `docs/SCIENTIFIC_WATER_INDICATORS.md` with formulas, units, provenance and scientific limits.

### Changed

- the Telegram report now distinguishes short-window `P−ET₀` from accumulated seasonal quantities;
- the water section is named “Осадки и атмосферная испаряемость” rather than implying measured root-zone water supply;
- a forecast row cannot displace a completed row for the same local calendar date;
- accumulated differences are calculated only from paired valid days;
- spell duration and 5-day precipitation are withheld whenever a calendar/value gap can hide the true sequence.

### Scientific limitations

- provider ET₀ is not actual crop evapotranspiration;
- `P−ET₀` is not root-zone storage, irrigation deficit or an irrigation dose;
- bounded-period dry spells and precipitation maxima are not presented as annual climate-normal indices;
- soil balance, `Kc/Ks`, SPI/SPEI and field validation remain future work.

## 2026-07-12 — scheduler lease and transaction failure orchestration

### Added

- reusable token-checked `RenewingLease` heartbeat guard;
- cancellation of protected provider/report work after lease ownership loss;
- real Redis test for a scheduler job running longer than its initial TTL;
- real Redis test for forced job-lock loss and safe retry by another worker;
- subprocess crash test proving lease recovery after TTL without explicit release;
- real PostgreSQL failure-injection after `flush` and before `COMMIT`;
- cancellation test preventing protected coroutines from continuing after caller shutdown.

### Changed

- frost and daily-digest job locks renew independently of field iteration;
- scheduler stops before starting another field after lease loss;
- `_lock_user` no longer commits before the enclosing state-changing operation;
- crop, season and manual-phase mutations use the same user row-lock transaction;
- user, field and crop-season onboarding records roll back together on pre-commit failure.

### Known limitation

- Telegram `sendMessage` has no application idempotency key. A process death after Telegram accepts a message but before Redis dedup persistence leaves an ambiguous external outcome; the project does not claim absolute exactly-once delivery for this boundary.

## 2026-07-12 — Telegram/FSM reliability

### Added

- testable production Dispatcher factory;
- full `field → crop → season → phase → report` Dispatcher scenario;
- real RedisStorage reopen test for the core FSM branches;
- global controlled handling for PostgreSQL, Redis and stale Telegram-message failures;
- correlation codes in user-safe dependency failure messages;
- regression test for all-field monitoring copy.

### Fixed

- manual phase selection no longer reads the removed `gdd_stages` structure;
- `/help` and field-list copy distinguish the active manual field from all enabled background-monitored fields;
- a deleted callback source message opens a fresh current menu instead of ending in an unhandled error.

## 2026-07-12 — field-readiness correctness

### Added

- explicit frost states: `risk_detected`, `no_risk_in_valid_forecast`, `insufficient_forecast_data`;
- fail-closed, per-field/day warning when forecast Tmin cannot be evaluated;
- provider model selection, retrieval timestamp and cache policy metadata;
- all-field background notification target query;
- local-morning digest scheduling by field timezone;
- PostgreSQL concurrent onboarding test;
- unit tests for strict local-date GDD boundary and missing forecast Tmin.

### Changed

- missing forecast Tmin no longer produces a green no-risk message;
- GDD excludes every local day before the configured season start;
- a seasonal GDD total requires a valid row on the start date;
- scheduler monitors every field with the relevant notification flag enabled;
- active field remains a manual Telegram navigation concept only;
- user creation uses PostgreSQL/SQLite upsert semantics;
- first field creation is serialized with a user row lock;
- daily digest runs hourly and sends only within the field local morning window;
- Open-Meteo model selection uses documented `auto` semantics;
- README, status, capability matrix and plan reflect verified behavior.

## 2026-07-11 — callback idempotency and scheduler workers

### Added

- Redis-backed callback delivery idempotency by `CallbackQuery.id`;
- short semantic anti-double-click lease by user, message and callback data;
- field-aware desired-state notification callbacks;
- fail-closed handling of legacy toggle buttons;
- real Redis callback and two-worker scheduler tests;
- retry verification after Telegram send failure.

### Changed

- settings callbacks encode final enabled/disabled state;
- stale-field callbacks are rejected;
- scheduler and callback middleware share one coordination backend.

## 2026-07-11 — real PostgreSQL and Redis verification

### Added

- PostgreSQL Alembic adoption/backfill tests;
- PostgreSQL row-lock and partial unique index tests;
- scheduler target tests on PostgreSQL;
- multi-client Redis lease/deduplication tests;
- aiogram RedisStorage restart test;
- `integration` pytest marker;
- CI with PostgreSQL and Redis system services, without Docker.

## 2026-07-10 — scientific integrity and repository cleanup

### Added

- read-only Open-Meteo contract smoke;
- production verification script;
- capability and status documents;
- explicit source/coverage metadata;
- optional RAG dependency profile.

### Changed

- current local day is forecast, not completed past;
- GDD, HTC, P−ET₀ and frost use explicit data partitions;
- unavailable P−ET₀/GDD values no longer become zero;
- frost messages do not claim an exact event hour;
- Open-Meteo cached resources close during shutdown.

### Removed

- synthetic Random Forest training and model claims;
- legacy launcher and Docker-only scripts/docs;
- unreachable heuristic recommender;
- unconnected ERA5, soil, satellite and storage prototypes;
- generated documentation with unsupported claims.

## 2026-07-10 — multi-field production flow

- aiogram-only runtime;
- PostgreSQL/Alembic field and season schema;
- Redis scheduler coordination;
- multiple fields and field-level notifications;
- native systemd deployment/update/rollback.
