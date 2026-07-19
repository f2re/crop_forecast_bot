# Матрица фактических возможностей

Дата актуализации: **2026-07-19**.

Статусы:

- ✅ production-code — доступно из Telegram-flow и покрыто тестами;
- 🟡 conditional — доступно только при проверяемых условиях;
- ⚪ optional — отдельный профиль зависимостей;
- ⛔ disabled — не реализовано или не валидировано.

| Возможность | Статус | Источник / метод | Поведение при отсутствии данных |
|---|---:|---|---|
| Несколько полей | ✅ | PostgreSQL `fields / crop_seasons` | поле не создаётся без валидных координат |
| Персистентный FSM | ✅ | RedisStorage | production не запускается без Redis |
| Callback idempotency | ✅ | Redis action leases | повтор не выполняет action второй раз |
| Оперативная погода | ✅ | Open-Meteo Forecast Best Match | явная ошибка без эвристической погоды |
| Сезонная история | 🟡 | Open-Meteo Historical Weather API | отчёт деградирует до доступного периода |
| Provider provenance | 🟡 | source/model/retrieval/cache metadata | неизвестные run/resolution не выдумываются |
| GDD | ✅ | daily-average method, crop `Tbase`, optional `Tupper` | `None` при отсутствии завершённого ряда |
| Сезонная сумма GDD | 🟡 | строго с локальной даты сезона | не заявляется без покрытия даты старта |
| Автоматическая фенофаза | ⛔ | пороги не валидированы | только наблюдение пользователя |
| ГТК Селянинова | 🟡 | сезонный непрерывный ряд, `Tср > 10°C` | скрывается без даты, при gap или <20 тёплых суток |
| Осадки − ET₀ | 🟡 | парные завершённые значения | пропуски не превращаются в ноль |
| Накопленные P/ET₀ | 🟡 | завершённые локальные сутки | forecast исключён, полнота проверяется раздельно |
| Сухие серии / Rx1day / Rx5day | 🟡 | ETCCDI threshold и continuity guards | не публикуются через calendar/value gap |
| Сезонное сравнение 1991–2020 | 🟡 | homogeneous ERA5 | основной отчёт продолжает работу без climate section |
| Общий climate period | ✅ | continuous prefix complete in `Tmean/P/ET₀` | ряд заканчивается до первого gap/missing value |
| Empirical percentiles | 🟡 | минимум 20 сопоставимых ERA5 years | не называются probability/SPI/SPEI |
| Прямая CDS pipeline | ⛔ | queued jobs/object cache отсутствуют | используется bounded Open-Meteo adapter |
| Deterministic frost screening | ✅ | прогнозная Tmin 2 м | отдельный `insufficient_forecast_data` |
| GFS multi-hazard monitor | ✅ | отдельные члены `gfs_seamless` | неполные сутки исключаются fail-closed |
| Ручной обзор рисков | ✅ | `/risks`, тот же domain calculation | controlled unavailable state |
| Автоматический compact risk digest | ✅ | APScheduler + Redis lease | один message на поле/цикл |
| Режим `immediate` | ✅ | state dedup | повтор того же состояния подавляется |
| Режим `digest` | ✅ | local-date dedup | один обычный digest в локальные сутки |
| Режим `high_only` | ✅ | фильтр `level=high` | watch/elevated не отправляются |
| Тихие часы | ✅ | local wall-clock presets | watch/elevated откладываются |
| High-risk bypass | ✅ | delivery policy | высокий риск не ждёт quiet hours/daily digest |
| История запусков риска | ✅ | `risk_forecast_runs/signals` | пустой журнал объясняется пользователю |
| Тренд риска | 🟡 | два последних запуска одной модели | не называется вероятностью или damage forecast |
| Delivery state | ✅ | `not_attempted/sending/sent/deduplicated/failed` | `sending` сохраняет ambiguous external outcome |
| Retention истории | ✅ | `RISK_HISTORY_RETENTION_DAYS` | default 90 суток |
| Ежедневный агроотчёт | ✅ | локальное утреннее окно поля | один report на поле/локальную дату |
| Pytest evidence | ✅ | GitHub Actions artifacts | unit/integration logs сохраняются 14 суток |
| RAG-поиск | ⚪ | ChromaDB + sentence-transformers | UI скрыт при `RAG_ENABLED=false` |
| LLM-ответ по RAG | ⚪ | OpenAI-compatible provider | отсутствие источника не подменяется генерацией |
| Полевой журнал | ⛔ | storage/Telegram flow отсутствуют | фактические наблюдения не сохраняются |
| Окно полевых работ | ⛔ | operation-specific policy отсутствует | suitability не генерируется |
| Official CAP warnings | ⛔ | adapters отсутствуют | модельный signal остаётся отдельным screening |
| Локальная метеостанция | ⛔ | ingestion/matching отсутствуют | bias/calibration не рассчитываются |
| SoilGrids | ⛔ | adapter отсутствует | почвенные показатели не показываются |
| Field polygon | ⛔ | поле хранится точкой | spatial monitoring не заявляется |
| Sentinel/MODIS NDVI/LAI | ⛔ | provider отсутствует | спутниковые индексы не показываются |
| SPI/SPEI | ⛔ | нет validated long-series distribution pipeline | не вычисляются из короткого прогноза |
| Crop/phase damage model | ⛔ | нормативная база отсутствует | не генерируется |
| Прогноз урожайности | ⛔ | нет реальной выборки и independent validation | отсутствует в runtime |
| Дозы препаратов/удобрений | ⛔ | нет проверяемого нормативного контекста | не генерируются |

## Инварианты данных

1. `reanalysis`, `operational_past`, `forecast` и climate reference не смешиваются.
2. Текущий локальный день относится к forecast.
3. Строки до локальной даты сезона не входят в сезонные накопления.
4. Forecast precipitation не входит в завершённый ГТК и накопленные показатели.
5. `NaN` и отрицательные водные значения не заменяются нулём.
6. Отсутствие Tmin или ensemble не интерпретируется как отсутствие риска.
7. Фаза пользователя маркируется как observation.
8. Неактивное поле мониторится, если alerts включены.
9. `ΣP−ΣET₀` вычисляется только по одинаковому набору парных суток.
10. Provider ET₀ не выдаётся за фактическую ET культуры, storage или irrigation dose.
11. Climate comparison использует fixed `era5`, а не mixed Best Match.
12. Current climate DTO содержит общий непрерывный period по `Tmean/P/ET₀`.
13. Empirical percentile и member fraction не считаются calibrated probability.
14. Accepted risk run записывается до Telegram side effect.
15. Provider failure и incomplete ensemble не создают successful history run.
16. Quiet hours влияют на delivery, но не удаляют accepted run.
17. High-risk bypass не меняет научный risk level.
18. Trend сравнивает одинаковые model/risk/event-date contracts.

## Внешние ограничения готовности

Статус ✅ означает подтверждённый production-code path, но не заменяет clean-host, real Telegram и regional station acceptance.
