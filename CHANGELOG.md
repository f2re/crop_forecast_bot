# Changelog

Все существенные изменения фиксируются здесь. Проект пока не использует стабильную SemVer-линейку.

## Unreleased — scientific integrity and repository cleanup

### Added

- read-only Open-Meteo contract smoke `python -m src.ops.provider_smoke`;
- production verification `scripts/verify-production.sh`;
- capability matrix and current status documents;
- explicit source/coverage metadata in calculations and reports;
- optional RAG dependency profile and runtime feature flag.

### Changed

- current local day is treated as forecast, not completed past;
- GDD, HTC, P−ET₀ and frost use explicit data partitions;
- unavailable P−ET₀/GDD values no longer become zero;
- frost messages no longer claim an exact event hour from daily data;
- README and runbooks describe only reachable production capabilities;
- Open-Meteo cached HTTP resources close during application shutdown.

### Removed

- synthetic Random Forest training and model claims;
- legacy `run_bot.py` launcher and Docker-only scripts/docs;
- unreachable heuristic recommender;
- unconnected ERA5, soil, satellite and legacy storage prototypes;
- stale generated marketing documentation with unsupported claims.

## 2026-07-10 — multi-field production flow

- aiogram-only runtime;
- PostgreSQL/Alembic field and season schema;
- Redis scheduler coordination;
- multiple fields and field-level notifications;
- native systemd deployment/update/rollback.
