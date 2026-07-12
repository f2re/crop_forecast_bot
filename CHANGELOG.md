# Changelog

Все существенные изменения фиксируются здесь. Проект пока не использует стабильную SemVer-линейку.

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
