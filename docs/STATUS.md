# Статус разработки

Дата актуализации: **2026-07-18**.

## Текущее состояние

PR #41 слит в `main`: ансамблевый scheduler теперь сохраняет принятые запуски и сигналы риска, фиксирует состояние доставки и показывает изменение между двумя последними запусками в Telegram-разделе **«История рисков»**.

Полный PR gate прошёл:

- Ruff и `compileall`;
- repository legacy/scientific-claims policies;
- unit/contract tests;
- PostgreSQL/Redis integration;
- backup/restore round trip;
- Alembic graph;
- live GFS Ensemble contract.

Проект готов на уровне **code-level полевого пилота**, но ещё не прошёл внешнюю полевую приёмку.

## Production-контур

```text
aiogram 3.x
PostgreSQL + SQLAlchemy 2 async + Alembic
Redis FSM / callback idempotency / renewable leases / deduplication
Open-Meteo Forecast + Historical Weather
Open-Meteo GFS Ensemble members
ERA5-Land current season + 1991–2020 reference
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
- [x] ручной 16-суточный обзор погодных рисков через `/risks`;
- [x] история и тренд рисков через `/history`;
- [x] настройки уведомлений по полю;
- [x] Redis FSM restart;
- [x] replay-safe callbacks;
- [x] controlled dependency failure UX.

### Данные и расчёты

- [x] раздельные `reanalysis / operational_past / forecast`;
- [x] GDD от локальной даты сезона с crop-specific `Tbase`;
- [x] сезонный ГТК только при непрерывном завершённом ряду;
- [x] provider ET₀ и `P−ET₀` без фиктивных нулей;
- [x] накопленные осадки/ET₀, сухие серии и Rx1day/Rx5day;
- [x] ERA5-Land current/reference одной моделью, база 1991–2020;
- [x] empirical percentiles без выдачи за probability/SPI/SPEI;
- [x] fail-soft climate section.

### Ансамблевые риски

- [x] GFS Ensemble Seamless, до 16 суток;
- [x] Tmin, Tmax, осадки, порывы и CAPE;
- [x] холод, жара, сильные осадки, ветер и конвективная неустойчивость;
- [x] минимум 20 валидных членов для каждой диагностической переменной;
- [x] fail-closed exclusion неполных суток;
- [x] `k/n`, P10, медиана, P90 и заблаговременность;
- [x] сырая доля ансамбля не называется откалиброванной вероятностью;
- [x] CAPE не называется прогнозом грозы или града;
- [x] background run каждые 6 часов;
- [x] Redis dedup по полю/риску/дате/уровню;
- [x] live GFS provider smoke и датированный evidence.

### Журнал и тренд риска

- [x] Alembic head `20260718_0004`;
- [x] `risk_forecast_runs` и `risk_forecast_signals`;
- [x] атомарное сохранение accepted run + signals до Telegram side effect;
- [x] идемпотентность по `field_id + model + retrieved_at`;
- [x] delivery states `not_attempted / sending / sent / deduplicated / failed`;
- [x] тренды `new / strengthening / stable / weakening / cleared`;
- [x] сравнение только двух последних запусков одной модели;
- [x] существенное изменение доли: 10 процентных пунктов;
- [x] retention через `RISK_HISTORY_RETENTION_DAYS`, default 90 суток;
- [x] Telegram formatter и Dispatcher flow.

Тренд отражает изменение модельного сигнала, а не вероятность события или ущерба.

### Надёжность и release engineering

- [x] PostgreSQL row locks и атомарные mutations;
- [x] renewable Redis leases;
- [x] отмена I/O после lease loss;
- [x] version-consistent code/unit rollback;
- [x] active + heartbeat verification;
- [x] PostgreSQL backup restore round trip;
- [x] live Open-Meteo, ERA5-Land и GFS contracts.

## Научные ограничения

- GFS и ERA5-Land — модельные сетки, не локальная станция.
- `k/n` требует архивной калибровки, прежде чем называться вероятностью.
- Журнал сохраняет threshold-crossing signals; для unbiased reliability analysis нужны также below-threshold evaluations и фактические наблюдения.
- Tmin воздуха 2 м не является температурой растения или crop damage model.
- Crop-specific `Tbase/Tupper` требуют versioned cultivar/region validation.
- Provider ET₀ не является фактической ET культуры или дозой полива.
- Валидированный прогноз града, болезней и урожайности отсутствует.
- SPI/SPEI по короткому прогнозу не вычисляются.

## Незакрытые внешние gates

- [ ] clean Debian 12 deploy, migration и reboot;
- [ ] real Telegram smoke для нескольких пользователей и полей;
- [ ] forced release failure и rollback на реальном systemd host;
- [ ] Astra Linux smoke;
- [ ] station comparison для GFS/ERA5-Land/ET₀/ГТК;
- [ ] screening-only регламент и независимый канал критических предупреждений.

## Следующие приоритеты

### P0

1. clean-host и real Telegram acceptance;
2. station comparison protocol;
3. operator runbook для неоднозначной Telegram delivery.

### P1

1. quiet hours и risk digest;
2. provider latency/error/cache/fallback metrics;
3. circuit breaker и stale-cache age;
4. совместимое переименование `frost_alerts_enabled` в `weather_risk_alerts_enabled`;
5. постепенное включение `mypy` и `bandit` в CI;
6. разделение перегруженных `scheduler.py` и `handlers/core.py` без универсальных framework-абстракций.

Подробный аудит: `docs/TECHNICAL_AUDIT_2026-07-18.md`.

## Готовность

**Code-level:** основной flow, агроотчёт, ансамблевые риски, ручной обзор и журнал тренда находятся в `main`; CI и live GFS gate зелёные.

**Полевой продукт:** не принят до clean-host, real Telegram и региональной станционной проверки.
