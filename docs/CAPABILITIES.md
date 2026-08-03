# Матрица фактических возможностей

Дата актуализации: **2026-08-03**.

Статусы:

- ✅ production-code — доступно из Telegram/runtime и покрыто тестами;
- 🟡 conditional — доступно только при проверяемых условиях;
- ⚪ optional — выключено в базовом MVP, включается отдельно;
- ⛔ disabled — не реализовано или не валидировано.

| Возможность | Статус | Источник / метод | Поведение при отсутствии данных |
|---|---:|---|---|
| Один aiogram entrypoint | ✅ | `python -m src.bot.main` | иной production launcher запрещён CI policy |
| Production startup-smoke | ✅ | DB + Redis + Router graph + scheduler | CI падает до unit tests |
| Telegram readiness | ✅ | реальный `getMe` до `READY=1` | release healthcheck не проходит |
| Несколько полей | ✅ | PostgreSQL `fields` | поле не создаётся без валидных координат |
| Несколько культур на точке | ✅ | несколько профилей `crop_seasons` | одна культура остаётся выбранной для отчёта |
| Отдельная дата/фаза культуры | ✅ | field-scoped crop profile | отсутствие даты блокирует только сезонные накопления |
| Inline-календарь | ✅ | Telegram inline keyboard | ручной ввод доступен как резерв |
| Будущая дата сезона | ⛔ | локальная дата поля | выбор и ручной ввод отклоняются |
| Безопасный Telegram HTML | ✅ | `SafeHtmlBot` + sanitizer | entity error повторяется один раз обычным текстом |
| Расчёт всех сохранённых fields | ✅ | startup cycle + APScheduler | обрабатываются только alert-enabled fields |
| Персистентный FSM | ✅ | RedisStorage | production не запускается без Redis |
| Callback idempotency | ✅ | Redis action leases | повтор не выполняет action второй раз |
| Оперативная погода | ✅ | Open-Meteo Forecast Best Match | явная ошибка без эвристической погоды |
| Сезонная история | 🟡 | Open-Meteo Historical Weather API | отчёт деградирует до доступного периода |
| Температура почвы 0–7 см | ✅ | `/soil`, Open-Meteo ECMWF Best Match | температура воздуха не подставляется вместо почвы |
| История температуры почвы | 🟡 | ERA5-Land 0–7 см через Open-Meteo | ряд скрывает неполные сутки и не заменяет пропуски нулём |
| Live soil-provider contract | ✅ | отдельный GitHub Actions smoke | изменение имени переменной или структуры API блокирует выпуск |
| Provider provenance | 🟡 | source/model/retrieval/cache metadata | неизвестные run/resolution не выдумываются |
| GDD | ✅ | daily-average method, crop `Tbase`, optional `Tupper` | `None` при отсутствии завершённого ряда |
| Сезонная сумма GDD | 🟡 | строго с локальной даты выбранной культуры | не заявляется без покрытия даты старта |
| Автоматическая фенофаза | ⛔ | пороги не валидированы | только наблюдение пользователя |
| ГТК Селянинова | 🟡 | сезонный непрерывный ряд, `Tср > 10°C` | скрывается без даты, при gap или <20 тёплых суток |
| Осадки − ET₀ | 🟡 | парные завершённые значения | пропуски не превращаются в ноль |
| Накопленные P/ET₀ | 🟡 | завершённые локальные сутки | forecast исключён, полнота проверяется раздельно |
| Сухие серии / Rx1day / Rx5day | 🟡 | ETCCDI threshold и continuity guards | не публикуются через calendar/value gap |
| Сезонное сравнение 1991–2020 | ⚪ | homogeneous ERA5 | production MVP не выполняет запрос при flag=false |
| Общий climate period | ✅ | continuous prefix complete in `Tmean/P/ET₀` | ряд заканчивается до первого gap/missing value |
| Empirical percentiles | 🟡 | минимум 20 сопоставимых ERA5 years | не называются probability/SPI/SPEI |
| Прямая CDS pipeline | ⛔ | queued jobs/object cache отсутствуют | используется bounded Open-Meteo adapter |
| Deterministic frost screening | ✅ | прогнозная Tmin 2 м | отдельный `insufficient_forecast_data` |
| GFS multi-hazard monitor | ✅ | отдельные варианты `gfs_seamless` | неполные сутки исключаются fail-closed |
| Startup risk cycle | ✅ | delay 120 s + тот же domain calculation | provider failure не останавливает polling |
| Плановый risk cycle | ✅ | каждые 6 часов + renewable lease | второй worker не выполняет тот же цикл |
| Один погодный запрос на точку | ✅ | coordinates-first provider call | добавление культуры не умножает API-запросы |
| Ручной обзор условий | ✅ | `/risks`, тот же domain calculation | controlled unavailable state |
| Группировка дней в период | ✅ | последовательные даты одного hazard | разрыв более суток создаёт новый период |
| Понятное физическое условие | ✅ | T2m/P/gust/CAPE threshold description | технические коды не выводятся как основное сообщение |
| Число вариантов модели | 🟡 | raw ensemble member count | называется согласованностью, не вероятностью ущерба |
| Основной разброс вариантов | 🟡 | P10–P90, описанный простыми словами | не называется доверительным интервалом наблюдаемой истины |
| Lead-aware приоритет | ✅ | level + lead time | дальний сигнал остаётся планированием |
| CAPE | 🟡 | max CAPE screening | не называется прогнозом грозы или града |
| Multi-crop risk context | ✅ | список культур точки | повреждение каждой культуры отдельно не рассчитывается |
| Автоматический compact risk digest | ✅ | APScheduler + Redis lease | одно сообщение на поле/цикл |
| Режим `immediate` | ✅ | state dedup | повтор того же состояния подавляется |
| Режим `digest` | ✅ | local-date dedup | один обычный digest в локальные сутки |
| Режим `high_only` | ✅ | фильтр `level=high` | watch/elevated не отправляются |
| Тихие часы | ✅ | local wall-clock presets | watch/elevated откладываются |
| High-priority bypass | ✅ | delivery policy | высокий приоритет не ждёт quiet hours/daily digest |
| История запусков риска | ✅ | `risk_forecast_runs/signals` | пустой журнал объясняется пользователю |
| Тренд риска | 🟡 | два последних запуска одной модели | не называется вероятностью или damage forecast |
| Delivery state | ✅ | `not_attempted/sending/sent/deduplicated/failed` | `sending` сохраняет ambiguous external outcome |
| Retention истории | ✅ | `RISK_HISTORY_RETENTION_DAYS` | production MVP default 30 суток |
| Ежедневный агроотчёт | ✅ | локальное утреннее окно поля | относится к выбранной культуре и выполняется при включении |
| Строгий каталог вредителей | ✅ | species + crop + biofix + driver + method + thresholds + source | культура без полного договора не получает вредителя в меню |
| Колорадский жук на картофеле | 🟡 | первая найденная кладка, воздух 2 м, daily average, 11,1°C | без находки расчёт не запускается |
| Совка ипсилон на кукурузе | 🟡 | значимый улов в ловушке, воздух 2 м, base 10°C | без ловушки и идентификации вида расчёт не запускается |
| Ростковая муха на кукурузе/сое | 🟡 | Jan 1, soil 0–7 см, single sine horizontal, 3,9/29°C | при неполном почвенном ряде расчёт скрывается |
| Pest scouting scheduler | ✅ | один local-morning цикл/сутки, renewable lease, event dedup | provider error не создаёт фиктивное окно и не останавливает polling |
| Pest treatment advice | ⛔ | наличие/численность/ЭПВ/регламент не вычисляются | препарат, срок, кратность и доза не генерируются |
| Green-main auto-update | ✅ | systemd timer + GitHub Actions gate | pending/failed/API error оставляет active release |
| Cheap update check | ✅ | `git ls-remote` до clone | тот же SHA не создаёт release |
| Atomic activation/rollback | ✅ | versioned symlink + heartbeat | восстанавливаются код и systemd units |
| Shared virtualenv | ✅ | hash Python minor + requirements | `pip install` только при изменении dependencies |
| PostgreSQL backup/restore | ✅ | `pg_dump/pg_restore` fingerprint | failed release сохраняет backup и откатывается |
| Low-resource thread profile | ✅ | executor=2, BLAS/OpenMP=1 | без неограниченного thread burst |
| Soft systemd controls | ✅ | MemoryHigh/weights/TasksMax | нет жёсткого MemoryMax |
| Python 3.10 compatibility | ✅ | отдельный CI job | Ubuntu 22.04 runtime проверяется non-integration suite |
| Pytest evidence | ✅ | GitHub Actions artifacts | validation logs сохраняются 14 суток |
| RAG-поиск | ⚪ | ChromaDB + sentence-transformers | Router не импортируется при flag=false |
| LLM-ответ по RAG | ⚪ | OpenAI-compatible provider | отсутствие источника не подменяется генерацией |
| Полевой журнал | ⛔ | storage/Telegram flow отсутствуют | фактические наблюдения не сохраняются |
| Окно полевых работ | ⛔ | operation-specific policy отсутствует | suitability не генерируется |
| Official CAP warnings | ⛔ | adapters отсутствуют | модельный signal остаётся отдельным screening |
| Локальная метеостанция | ⛔ | ingestion/matching отсутствуют | bias/calibration не рассчитываются |
| SoilGrids | ⛔ | adapter отсутствует | статические почвенные показатели не показываются |
| Field polygon | ⛔ | поле хранится точкой | spatial monitoring не заявляется |
| Sentinel/MODIS NDVI/LAI | ⛔ | provider отсутствует | спутниковые индексы не показываются |
| SPI/SPEI | ⛔ | нет validated long-series distribution pipeline | не вычисляются из короткого прогноза |
| Crop/phase damage model | ⛔ | нормативная база отсутствует | не генерируется |
| Прогноз урожайности | ⛔ | нет реальной выборки и independent validation | отсутствует в runtime |
| Дозы препаратов/удобрений | ⛔ | нет проверяемого нормативного контекста | не генерируются |

## Инварианты данных и эксплуатации

1. `reanalysis`, `operational_past`, `forecast` и climate reference не смешиваются.
2. Текущий локальный день относится к forecast.
3. Строки до локальной даты сезона выбранной культуры не входят в накопления.
4. Forecast precipitation не входит в завершённый ГТК и накопленные показатели.
5. `NaN` и отрицательные водные значения не заменяются нулём.
6. Отсутствие Tmin или ensemble не интерпретируется как отсутствие риска.
7. Фаза пользователя маркируется как observation конкретной культуры.
8. Дополнительная культура не создаёт отдельный погодный запрос для той же точки.
9. Неактивное поле мониторится, если alerts включены.
10. `ΣP−ΣET₀` вычисляется только по одинаковому набору парных суток.
11. Provider ET₀ не выдаётся за фактическую ET культуры, storage или irrigation dose.
12. Climate comparison использует fixed `era5`, а не mixed Best Match.
13. Current climate DTO содержит общий непрерывный period по `Tmean/P/ET₀`.
14. Empirical percentile и member fraction не считаются calibrated probability.
15. Согласованность членов одного запуска не называется временной устойчивостью прогноза.
16. CAPE не считается достаточным условием грозы или града.
17. Accepted risk run записывается до Telegram side effect.
18. Provider failure и incomplete ensemble не создают successful history run.
19. Quiet hours влияют на delivery, но не удаляют accepted run.
20. High-priority bypass не меняет научный risk level.
21. Trend сравнивает одинаковые model/risk/event-date contracts.
22. Telegram readiness не заявляется до реального `getMe`.
23. Любой runtime HTML-текст экранируется до Telegram API; entity error имеет plain-text fallback.
24. Auto-update не активирует SHA без green required CI.
25. Branch race после gate завершает update без активации непроверенного SHA.
26. PostgreSQL и Redis остаются обязательным MVP storage/coordination контуром.
27. Вредитель связывается с культурой только через версионированный договор «вид — культура — точка отсчёта — показатель — метод — пороги — источник».
28. Температура воздуха и температура почвы являются разными drivers и не подставляются друг вместо друга.
29. Температура почвы 0–7 см маркируется как модельный слой, а не датчик на глубине посева.
30. Прогнозная температура не входит в уже накопленную сумму развития вредителя; она используется только для ориентировочной даты следующего окна.
31. Неполный завершённый температурный ряд скрывает pest outlook вместо заполнения пропусков.
32. Calendar pest model ежегодно получает новую дату 1 января и сбрасывает старые delivery tokens.
33. Pest outlook не называется presence, infestation, damage probability или treatment requirement.
34. Все модели одной точки используют не более одного запроса на каждый требуемый температурный driver за цикл.

## Внешние ограничения готовности

Статус ✅ означает подтверждённый production-code path, но не заменяет повторный real Telegram smoke, clean-host update/rollback и regional station acceptance.
