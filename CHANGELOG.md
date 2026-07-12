# Changelog

Все существенные изменения фиксируются здесь. Проект пока не использует стабильную SemVer-линейку.

## Unreleased — field-readiness correctness

### Added

- explicit frost states: `risk_detected`, `no_risk_in_valid_forecast`, `insufficient_forecast_data`;
- provider model configuration, retrieval timestamp and cache policy metadata;
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
