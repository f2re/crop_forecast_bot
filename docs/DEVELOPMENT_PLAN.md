# План модернизации Crop Forecast Bot

Дата актуализации: **2026-07-18**.

## Цель ближайшего релиза

Довести бот до воспроизводимого полевого пилота: один aiogram 3.x runtime, устойчивое хранение состояния, научно ограниченные агрометеорологические показатели, доступный вручную обзор рисков и автоматические предупреждения с прозрачной неопределённостью.

Бот не подменяет официальные предупреждения, локальную метеостанцию, агрономическое обследование или нормативную инструкцию к препарату.

## Фактическое состояние

### Подтверждено кодом, CI и live-контрактами

- единый entrypoint `python -m src.bot.main` на aiogram 3.x;
- PostgreSQL + SQLAlchemy 2 async + Alembic;
- Redis FSM, callback idempotency, renewable scheduler leases и deduplication;
- несколько полей, культура, дата сезона и ручная фенологическая фаза;
- Open-Meteo Forecast/Historical Weather;
- однородное ERA5-Land сравнение текущего сезона с базой 1991–2020;
- GDD, сезонный ГТК, provider ET₀, `P−ET₀`, накопленные осадки, сухие серии и Rx1day/Rx5day;
- GFS Ensemble-контур пяти погодных рисков;
- live GFS contract: 31 член, 16 последовательных локальных суток, полное покрытие диагностик;
- ручной обзор рисков из Telegram через кнопку и `/risks`;
- versioned systemd releases, heartbeat, verified rollback и backup/restore evidence.

### Не подтверждено внешней приёмкой

- clean Debian 12/Astra Linux deploy и reboot;
- real Telegram-flow с production token для нескольких пользователей и полей;
- forced rollback на реальном systemd host;
- региональная проверка GFS, ERA5-Land, ET₀ и ГТК по локальным станциям;
- откалиброванные вероятности рисков и crop-specific damage thresholds;
- валидированный прогноз града, болезней или урожайности.

## Целевая архитектура

```text
Telegram / aiogram Router + Redis FSM
        ↓
application services / typed ports
        ↓
domain / scientifically bounded calculations
        ↓
infrastructure adapters
  ├─ Open-Meteo operational forecast/history
  ├─ Open-Meteo GFS Ensemble members
  ├─ ERA5-Land current season + 1991–2020 reference
  ├─ PostgreSQL repositories / Alembic
  ├─ Redis leases / deduplication / coordination
  └─ optional source-attributed RAG
        ↓
APScheduler + versioned systemd release + heartbeat
```

## Инварианты

1. Один Telegram framework и один entrypoint.
2. Handlers не выполняют расчёты, HTTP или блокирующий I/O.
3. Все I/O-контракты асинхронные и типизированные.
4. PostgreSQL — source of truth; Redis — FSM и coordination.
5. Observation, reanalysis, forecast и climate reference не смешиваются.
6. Пропуск не превращается в ноль, безопасность или синтетический fallback.
7. Формула имеет источник, единицы, период, область применимости и тесты.
8. Сырая доля ансамбля `k/n` не называется откалиброванной вероятностью.
9. CAPE не называется прогнозом грозы или града.
10. Фоновый мониторинг охватывает все явно включённые поля.
11. Side effects прекращаются после потери scheduler lease.
12. State-changing callback задаёт конечное состояние, а не toggle.
13. Код, systemd-unit, миграции и healthcheck рассматриваются как один release.
14. Функция считается готовой только после Telegram-сценария и тестов.

## Завершённый вертикальный срез — ручной обзор погодных рисков

Статус: **слито в `main` через PR #39; полный CI зелёный; новые формулы и пороги не вводились**.

### Причина

Scheduler уже рассчитывал пять ансамблевых рисков, но пользователь не мог самостоятельно запросить единый текущий обзор для активного поля.

### Реализовано

- кнопка **«Погодные риски»** в главном меню и карточке активного поля;
- команда `/risks`;
- отдельный aiogram Router;
- application service поверх существующего `RiskForecastProvider`;
- тот же `calc_ensemble_risks`, что используется scheduler;
- до пяти наиболее значимых событий;
- `k/n`, P10, медиана, P90, заблаговременность, покрытие и provenance;
- структура ответа: что происходит → насколько надёжно → что делать → когда проверить снова;
- fail-closed при неполном ансамбле или отказе провайдера;
- лимит Telegram 4096 символов;
- Dispatcher-flow `поле → культура → ручной обзор рисков`.

### Проверено

- static и scientific-claims policy checks;
- unit/contract tests;
- PostgreSQL/Redis integration;
- backup/restore round trip;
- Alembic graph;
- существующие live-provider contracts.

## Активный следующий вертикальный срез — журнал и тренд риска

Приоритет: **P1**.

### Причина

Без сохранения последовательных прогнозов невозможно:

- показать усиление или ослабление сигнала;
- отличить новый риск от повторного уведомления;
- доказать качество работы бота;
- построить Brier/reliability/ROC/PR;
- выполнить региональную калибровку.

### Схема данных

Добавить Alembic migration и таблицы:

```text
risk_forecast_runs
- id
- field_id
- provider/source/model
- retrieved_at/model_run
- timezone
- member_count/forecast_days
- created_at

risk_forecast_signals
- run_id
- risk_type/event_date/lead_days/level
- members_exceeding/valid_members/member_fraction
- severe fraction
- threshold/severe_threshold/unit
- p10/median/p90
- notified_at/delivery_state
```

Инварианты:

- уникальность run по `field_id + model + retrieved_at`;
- сигналы одного run записываются одной транзакцией;
- provider failure не создаёт ложный успешный run;
- scheduler не отправляет сообщение до успешного сохранения run/signals;
- Telegram ambiguity хранится отдельным delivery state;
- retention policy задаётся конфигурацией.

### Логика тренда

Для одинаковых `field + risk_type + event_date` сравнивать два последних run:

- `new` — раньше сигнала не было;
- `strengthening` — fraction/level выросли выше минимального изменения;
- `stable` — изменение ниже порога;
- `weakening` — fraction/level снизились;
- `cleared` — сигнал был, теперь ниже порога.

Тренд не является вероятностной калибровкой. Это только изменение модельного ансамблевого сигнала между запусками.

### Telegram UX

- раздел **«История рисков»**;
- последние события по активному полю;
- дата запуска и источник;
- отметка «новый / усиливается / стабилен / ослабевает / снят»;
- кнопка обновления без повторной отправки старых событий;
- компактный журнал, без выгрузки всех членов ансамбля.

### Тесты

- Alembic fresh/upgrade/downgrade graph;
- idempotent run insert;
- atomic run + signals rollback;
- two-worker scheduler competition;
- trend boundary tests;
- timezone/event-date tests;
- Telegram history flow;
- retention cleanup;
- provider failure and ambiguous delivery state.

## Последующие срезы

### 1. Quiet hours и risk digest

- локальные часы тишины поля;
- режимы «сразу», «дайджест», «только высокий риск»;
- объединение нескольких рисков в одно сообщение;
- DST/timezone tests;
- запрет доставки просроченного события после quiet hours.

### 2. Эксплуатационная приёмка

- clean Debian 12 deploy/reboot/update/rollback;
- real Telegram smoke для двух пользователей и нескольких полей;
- Astra Linux smoke;
- message/log/screenshot evidence;
- operator runbook для неоднозначного результата Telegram send.

### 3. Станционная проверка и калибровка

- импорт наблюдений локальной станции;
- forecast run ↔ observation matching;
- bias, MAE/RMSE для непрерывных величин;
- contingency table, POD/FAR/CSI для событий;
- Brier score и reliability diagram для member fractions;
- отдельная калибровка по риску, сроку, сезону и региону.

### 4. Окно полевых работ

- осадки, ветер, температура, влажность и предшествующее увлажнение;
- отдельное окно опрыскивания только как метеоограничение;
- ссылка на этикетку/регламент вместо генерации дозировок;
- объяснение причины подходящего или неподходящего окна.

### 5. Почвенно-водный контур

- SoilGrids adapter и ocean/no-data guards;
- локальная FAO-56 при полном наборе входов;
- validated `Kc/Ks`;
- root-zone storage, фактический полив, runoff/infiltration assumptions;
- полевая валидация и явная неопределённость.

### 6. Спутниковый мониторинг

- Sentinel-2/MODIS provider;
- SCL/cloud/water/quality masks;
- NDVI/LAI при достаточном quality coverage;
- сравнение поля с собственной историей;
- temporal consistency до уведомления об аномалии.

## Сопутствующий технический долг

- актуализировать README и `docs/CAPABILITIES.md` под GFS Ensemble и `/risks`;
- совместимой миграцией переименовать `frost_alerts_enabled` в `weather_risk_alerts_enabled`;
- добавить архивирование/удаление поля и экспорт пользовательских данных;
- добавить provider latency/error/cache/fallback metrics;
- реализовать circuit breaker, измеримый rate limiter и stale-cache age;
- versioned sources для crop-specific `Tbase/Tupper`.

## Definition of Done ближайшего релиза

- ручной обзор доступен из production Router graph;
- основной CI зелёный;
- live GFS contract остаётся зелёным;
- расчёты и тексты не вводят новые научные claims;
- audit и development plan синхронизированы;
- clean-host, real Telegram и station-validation gates перечислены явно.
