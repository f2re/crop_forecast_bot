# Статус разработки

Дата актуализации: **2026-07-19**.

## Текущее состояние

PR #43 добавляет per-field режимы доставки погодных рисков, локальные тихие часы и один compact multi-hazard digest. В ходе live acceptance также исправлены два внешних provider contract:

- generic Open-Meteo Forecast использует Best Match по умолчанию без устаревшего `models=auto`;
- climate current/reference использует одну фиксированную ERA5-конфигурацию и общий непрерывный период, полный по температуре, осадкам и ET₀.

Полный PR gate прошёл на текущем коде:

- Ruff и `compileall`;
- repository legacy/scientific-claims policies;
- unit/contract tests;
- PostgreSQL/Redis integration;
- pytest log artifacts;
- backup/restore round trip;
- Alembic graph;
- live operational Open-Meteo contract;
- live homogeneous ERA5 contract;
- live GFS Ensemble contract.

Проект готов на уровне **code-level полевого пилота**, но ещё не прошёл внешнюю полевую приёмку.

## Production-контур

```text
aiogram 3.x
PostgreSQL + SQLAlchemy 2 async + Alembic
Redis FSM / callback idempotency / renewable leases / deduplication
Open-Meteo Forecast Best Match + Historical Weather
Open-Meteo GFS Ensemble members
ERA5 current season + 1991–2020 reference
APScheduler
systemd + versioned releases + heartbeat + verified rollback
```

## Подтверждённые возможности

### Telegram

- [x] один entrypoint `python -m src.bot.main`;
- [x] несколько полей;
- [x] геолокация и ручные координаты;
- [x] культура, дата сезона и наблюдаемая фаза;
- [x] ручной агроотчёт;
- [x] ручной 16-суточный обзор рисков через `/risks`;
- [x] история и тренд через `/history`;
- [x] настройки уведомлений по полю;
- [x] режимы `immediate / digest / high_only`;
- [x] тихие часы `off / 22:00–07:00 / 23:00–06:00`;
- [x] высокий риск обходит тихие часы и ожидание digest;
- [x] Redis FSM restart и replay-safe callbacks.

### Данные и расчёты

- [x] раздельные `reanalysis / operational_past / forecast`;
- [x] GDD от локальной даты сезона с crop-specific `Tbase`;
- [x] сезонный ГТК только при непрерывном завершённом ряду;
- [x] provider ET₀ и `P−ET₀` без фиктивных нулей;
- [x] накопленные осадки/ET₀, сухие серии и Rx1day/Rx5day;
- [x] ERA5 current/reference одной моделью, база 1991–2020;
- [x] общий полный current climate prefix для `Tmean/P/ET₀`;
- [x] empirical percentiles без выдачи за probability/SPI/SPEI;
- [x] fail-soft climate section.

### Ансамблевые риски

- [x] GFS Ensemble Seamless, до 16 суток;
- [x] Tmin, Tmax, осадки, порывы и CAPE;
- [x] холод, жара, сильные осадки, ветер и конвективная неустойчивость;
- [x] минимум 20 валидных членов по всем диагностическим переменным;
- [x] fail-closed exclusion неполных суток;
- [x] `k/n`, P10, медиана, P90 и заблаговременность;
- [x] `k/n` не называется откалиброванной вероятностью;
- [x] CAPE не называется прогнозом грозы или града;
- [x] background run каждые 6 часов;
- [x] один digest на поле вместо серии сообщений;
- [x] state/daily deduplication;
- [x] live GFS provider smoke.

### Журнал и доставка

- [x] Alembic head `20260719_0005`;
- [x] `risk_forecast_runs` и `risk_forecast_signals`;
- [x] accepted run + signals сохраняются до Telegram side effect;
- [x] идемпотентность по `field_id + model + retrieved_at`;
- [x] delivery states `not_attempted / sending / sent / deduplicated / failed`;
- [x] тренды `new / strengthening / stable / weakening / cleared`;
- [x] retention через `RISK_HISTORY_RETENTION_DAYS`, default 90 суток;
- [x] quiet-hours decision не удаляет run и не превращает его в «нет риска».

### Надёжность и release engineering

- [x] PostgreSQL row locks и атомарные mutations;
- [x] renewable Redis leases;
- [x] отмена I/O после lease loss;
- [x] version-consistent code/unit rollback;
- [x] active + heartbeat verification;
- [x] PostgreSQL backup restore round trip;
- [x] pytest failure logs как artifact;
- [x] live Open-Meteo, ERA5 и GFS contracts.

## Научные ограничения

- GFS и ERA5 — модельные сетки, не локальная станция.
- `k/n` требует архивной калибровки, прежде чем называться вероятностью.
- Risk history сохраняет threshold-crossing events; для unbiased reliability нужны below-threshold evaluations и observations.
- Tmin воздуха 2 м не является температурой растения или damage model.
- Crop-specific `Tbase/Tupper` требуют versioned cultivar/region validation.
- Provider ET₀ не является фактической ET культуры или дозой полива.
- Валидированный прогноз града, болезней и урожайности отсутствует.
- SPI/SPEI по короткому прогнозу не вычисляются.

## Незакрытые внешние gates

- [ ] clean Debian 12 deploy, migration и reboot;
- [ ] real Telegram smoke для нескольких пользователей и полей;
- [ ] forced release failure и rollback на реальном systemd host;
- [ ] Astra Linux smoke;
- [ ] station comparison для GFS/ERA5/ET₀/ГТК;
- [ ] screening-only регламент и независимый официальный канал.

## Следующие приоритеты

### P0

1. clean-host и real Telegram acceptance;
2. station comparison protocol;
3. operator runbook;
4. полевой журнал наблюдений и операций.

### P1

1. окно полевых работ;
2. official CAP warning layer;
3. provider latency/error/cache/fallback metrics;
4. circuit breaker и stale-cache age;
5. station ingestion и forecast matching;
6. below-threshold evaluations;
7. переименование `frost_alerts_enabled`;
8. разделение `scheduler.py` и `handlers/core.py`;
9. постепенные mypy/Bandit gates.

Подробный аудит: `docs/DEEP_AUDIT_2026-07-19.md`.

## Готовность

**Code-level:** основной flow, агроотчёт, ансамблевые риски, история, digest и quiet hours реализованы и проходят CI/live contracts.

**Полевой продукт:** не принят до clean-host, real Telegram и региональной station validation.
