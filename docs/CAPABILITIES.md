# Матрица фактических возможностей

Дата актуализации: **2026-07-18**.

Статусы:

- ✅ production-code — доступно из Telegram-flow и покрыто тестами;
- 🟡 conditional — доступно только при проверяемых условиях;
- ⚪ optional — отдельный профиль зависимостей;
- ⛔ disabled — не реализовано или не валидировано.

| Возможность | Статус | Источник / метод | Поведение при отсутствии данных |
|---|---:|---|---|
| Несколько полей | ✅ | PostgreSQL `fields` / `crop_seasons` | поле не создаётся без валидных координат |
| Персистентный FSM | ✅ | RedisStorage | production не запускается без Redis |
| Callback idempotency | ✅ | Redis delivery/action leases | повтор не выполняет action второй раз |
| Оперативная погода | ✅ | Open-Meteo Forecast API | явная ошибка без эвристической погоды |
| Сезонная история | 🟡 | Open-Meteo Historical Weather API | отчёт деградирует до доступного периода |
| Provider provenance | 🟡 | source/model/retrieval/cache metadata | неизвестные model run/resolution не выдумываются |
| ГДД | ✅ | daily-average method, crop `Tbase`, optional `Tupper` | `None` при отсутствии завершённого ряда |
| Сезонная сумма ГДД | 🟡 | строго с локальной даты сезона | не заявляется без покрытия даты старта |
| Автоматическая фенофаза | ⛔ | пороги не валидированы | только наблюдение пользователя |
| ГТК Селянинова | 🟡 | сезонный непрерывный ряд, `Tср > 10°C` | скрывается без даты сезона, при gap или <20 тёплых суток |
| Осадки − ET₀ | 🟡 | парные завершённые значения | пропуски не превращаются в ноль |
| Накопленные P/ET₀ | 🟡 | завершённые локальные сутки | forecast исключён, полнота проверяется раздельно |
| Сухие серии / Rx1day / Rx5day | 🟡 | ETCCDI-порог и continuity guards | не публикуются через календарный/value gap |
| Сезонное сравнение 1991–2020 | 🟡 | homogeneous ERA5-Land | основной отчёт продолжает работу без climate section |
| Empirical percentiles | 🟡 | минимум 20 сопоставимых ERA5-Land лет | не называются probability/SPI/SPEI |
| Прямая CDS pipeline | ⛔ | queued jobs/object cache отсутствуют | используется bounded Open-Meteo adapter |
| Deterministic frost screening | ✅ | прогнозная Tmin 2 м | отдельный `insufficient_forecast_data` |
| GFS multi-hazard monitor | ✅ | отдельные члены `gfs_seamless` | неполные сутки исключаются fail-closed |
| Ручной обзор рисков | ✅ | `/risks`, тот же domain calculation | показывает controlled unavailable state |
| Автоматические risk alerts | ✅ | APScheduler + renewable Redis lease | все enabled fields, dedup по event |
| История запусков риска | ✅ | PostgreSQL `risk_forecast_runs/signals` | пустой журнал объясняется пользователю |
| Тренд риска | 🟡 | сравнение двух последних запусков одной модели | не называется вероятностью или прогнозом ущерба |
| Delivery state | ✅ | `not_attempted/sending/sent/deduplicated/failed` | `sending` сохраняет неоднозначный внешний outcome |
| Retention истории | ✅ | `RISK_HISTORY_RETENTION_DAYS` | default 90 суток |
| Daily digest | ✅ | локальное утреннее окно поля | один digest на поле/локальную дату |
| Quiet hours / risk digest | ⛔ | не реализовано | alerts отправляются по текущей политике |
| RAG-поиск | ⚪ | ChromaDB + sentence-transformers | UI скрыт при `RAG_ENABLED=false` |
| LLM-ответ по RAG | ⚪ | OpenAI-compatible provider | отсутствие источника не подменяется генерацией |
| SoilGrids | ⛔ | adapter отсутствует | почвенные показатели не показываются |
| Sentinel/MODIS NDVI/LAI | ⛔ | provider отсутствует | спутниковые индексы не показываются |
| SPI/SPEI | ⛔ | нет validated long-series distribution pipeline | не вычисляются из короткого прогноза |
| Crop/phase damage model | ⛔ | нормативная база отсутствует | не генерируется |
| Прогноз урожайности | ⛔ | нет реальной выборки и независимой валидации | отсутствует в runtime |
| Дозы препаратов/удобрений | ⛔ | нет проверяемого нормативного контекста | не генерируются |

## Инварианты данных

1. `reanalysis`, `operational_past`, `forecast` и climate reference не смешиваются.
2. Текущий локальный день относится к прогнозу.
3. Строки до локальной даты сезона не входят в сезонные накопления.
4. Forecast precipitation не входит в завершённый ГТК и накопленные показатели.
5. `NaN` и отрицательные водные значения не заменяются фиктивным нулём.
6. Отсутствие Tmin или ансамбля не интерпретируется как отсутствие риска.
7. Фаза пользователя маркируется как наблюдение.
8. Неактивное поле мониторится, если alerts включены.
9. `ΣP−ΣET₀` вычисляется только по одинаковому набору парных суток.
10. Provider ET₀ не выдаётся за фактическую ET культуры, влагозапас или дозу полива.
11. Climate comparison использует фиксированный `era5_land`, а не mixed Best Match.
12. Empirical percentile и member fraction не интерпретируются как откалиброванная вероятность.
13. Accepted risk run записывается до Telegram side effect.
14. Provider failure и неполный ensemble не создают успешный history run.
15. Trend сравнивает только одинаковые model/risk/event-date contracts.

## Внешние ограничения готовности

Статус ✅ означает подтверждённый production-code path, но не заменяет clean-host, real Telegram и региональную станционную приёмку.
