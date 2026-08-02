# План модернизации Crop Forecast Bot

Дата актуализации: **2026-08-02**.

## Цель ближайшего релиза

Перевести проверенный code-level MVP в контролируемый полевой пилот на слабом сервере:

1. подтвердить получение зелёного `main` целевым сервером;
2. повторить реальный Telegram-flow нескольких полей и культур;
3. начать накапливать фактические наблюдения пользователя;
4. не увеличивать runtime и dependency surface без измеримой пользы.

Бот не подменяет официальные предупреждения, локальную метеостанцию, агрономическое обследование или нормативную инструкцию к препарату.

## Подтверждённое состояние

- один aiogram 3.x entrypoint;
- PostgreSQL + SQLAlchemy 2 async + Alembic;
- Redis FSM, callback idempotency, renewable leases и deduplication;
- несколько полей и несколько культур на одной координатной точке;
- отдельные дата посева и ручная фаза каждой культуры;
- inline-календарь и ручной резервный ввод даты;
- Open-Meteo Forecast Best Match/Historical Weather;
- GDD, сезонный ГТК, provider ET₀, `P−ET₀`, накопления и precipitation extremes;
- GFS Ensemble multi-hazard screening;
- farmer-facing `/risks`, risk history `/history`;
- delivery modes, quiet hours и compact digest;
- глобальная защита Telegram HTML;
- versioned systemd release, heartbeat, rollback и backup/restore;
- low-resource production profile;
- pull-based green-main CD;
- Python 3.10 compatibility gate.

Опциональные ERA5 1991–2020 и RAG сохранены, но выключены в production MVP.

## Архитектурные инварианты

1. Один Telegram framework и один entrypoint.
2. Handlers не выполняют формулы, HTTP и блокирующий I/O.
3. Все внешние I/O-контракты асинхронные и типизированные.
4. PostgreSQL — source of truth; Redis — FSM и coordination.
5. Observation, reanalysis, forecast и climate reference не смешиваются.
6. Пропуск не превращается в ноль, безопасность или synthetic fallback.
7. Формула имеет источник, единицы, период, область применимости и тесты.
8. Число членов ансамбля не называется calibrated probability.
9. Согласованность одного запуска не называется временной устойчивостью прогноза.
10. CAPE не называется прогнозом грозы или града.
11. Погодный запрос относится к координатной точке и не дублируется для каждой культуры.
12. Дата, фаза и сезонные накопления относятся к выбранной культуре.
13. Background monitoring охватывает все явно enabled fields.
14. Side effects прекращаются после потери scheduler lease.
15. Accepted risk run сохраняется до delivery decision и Telegram side effect.
16. Quiet hours влияют на delivery, но не на scientific result/history.
17. State-changing callback задаёт конечное состояние, а не toggle.
18. Runtime HTML экранируется до Telegram API и имеет plain-text fallback.
19. Код, systemd units, migrations и healthcheck образуют один release.
20. Systemd readiness требует реального Telegram `getMe`.
21. Автообновление `main` выполняется только после green CI точного SHA.
22. Функция готова только после Telegram-flow и тестов.

## Завершённые вертикальные срезы

### Ручной обзор риска — PR #39

- кнопка и `/risks`;
- общий domain calculation;
- raw ensemble distribution, lead time и provenance;
- fail-closed UX.

### Журнал прогноза и тренд — PR #41

- `risk_forecast_runs/signals`;
- atomic accepted run + signals;
- delivery states;
- `new / strengthening / stable / weakening / cleared`;
- retention;
- `/history`.

### Quiet hours и risk digest — PR #43

- `immediate / digest / high_only`;
- local quiet hours;
- один multi-hazard message;
- high-priority bypass;
- accepted run независимо от delivery;
- Alembic head `20260719_0005`.

### Низкоресурсный MVP и green-main CD — PR #44

- реальный Telegram `getMe` до `READY=1`;
- `python -m src.bot.main --startup-smoke` для CI;
- bounded `asyncio.to_thread` executor;
- RAG Router не импортируется при disabled feature;
- первый risk cycle всех сохранённых полей после здорового старта;
- timer каждые 15 минут;
- exact-SHA GitHub Actions gate;
- shallow clone после gate и branch-race check;
- content-addressed shared virtualenv;
- backup/migrate/preflight/activate/rollback;
- low-resource systemd profile.

### Исправление native deploy — PR #45 и #46

- scoped `umask` для секретного environment;
- relocatable shared virtualenv и `python -m alembic`;
- runtime paths нормализуются для пользователя `cropbot`;
- `/run/crop-forecast-bot` создаётся до preflight;
- deploy diagnostics и Python 3.10 gate.

### Farmer UX: календарь, несколько культур, безопасный отчёт и понятные риски — PR #47

#### Дата

- inline-календарь без Mini App и веб-сервера;
- переход по месяцам и годам;
- будущие даты недоступны;
- прошлый год доступен для озимых;
- ручной ввод и отмена сохранены.

#### Культуры

- несколько crop profiles на одной координатной точке;
- одна культура выбрана для текущего отчёта;
- отдельные дата и наблюдаемая фаза каждой культуры;
- повторное добавление выбирает существующий профиль;
- единственную культуру удалить нельзя;
- отдельный погодный запрос для каждой культуры не создаётся.

#### Telegram и отчёт

- глобальный `SafeHtmlBot`;
- экранирование случайных `<`, `>` и `&`;
- plain-text retry при Telegram entity error;
- отдельный report Router и команда `/report`.

#### Погодные сигналы

- последовательные дни одного явления объединяются в период;
- техническое «пересечение порога» заменено физическим описанием условия;
- доля членов не показывается как вероятность ущерба;
- P10–P90 объясняется как основной разброс вариантов;
- action priority учитывает lead time;
- дальний сигнал остаётся планированием;
- CAPE не выдаётся за прогноз града;
- в сообщении перечисляются культуры точки без damage claim.

#### Проверки

- calendar parsing/navigation/future-date guards;
- separate multi-crop dates/phases и unique selected profile;
- SafeHtmlBot sanitizer/fallback contract;
- grouped and lead-aware risk language;
- dispatcher crop/date/report/risk scenarios;
- multi-crop scheduler digest;
- Python 3.10, PostgreSQL/Redis и production startup gates.

## Активный следующий кодовый срез — полевой журнал

### Причина

Новые модельные индексы без фактических наблюдений дают ограниченную добавочную ценность. Полевой журнал создаёт контекст для рекомендаций, station validation, water balance и оценки полезности alerts.

### Минимальная схема

```text
field_observations
- id
- field_id
- crop_season_id nullable
- observed_at
- observation_type
- numeric_value nullable
- unit nullable
- note nullable
- source
- created_at
```

Первый набор `observation_type`:

```text
phase
operation
irrigation
rain_gauge
station_tmin
station_tmax
damage
note
```

### Telegram UX

- кнопка **«Журнал поля»**;
- список последних записей;
- добавление через короткий FSM;
- выбор: наблюдение относится ко всему полю или выбранной культуре;
- удаление только собственной записи;
- локальное время поля;
- единицы и допустимые диапазоны;
- `/journal` как дополнительная команда;
- без автоматической интерпретации повреждения.

### Инварианты

- запись принадлежит конкретному field;
- crop-specific observation при необходимости ссылается на crop profile;
- observation time timezone-aware на входе и хранится UTC;
- user source маркируется явно;
- irrigation/rain values не смешиваются с model precipitation;
- station temperature не заменяет provider series автоматически;
- photo/file reference optional и не анализируется в первом срезе;
- no free-form pesticide/fertilizer dosing logic.

### Тесты

- Alembic fresh/upgrade/downgrade;
- ownership и cascade delete;
- field/crop scope;
- value/unit validation;
- timezone/DST;
- restart-safe FSM;
- duplicate callback protection;
- Telegram add/list/delete scenario;
- PostgreSQL integration;
- message length.

## P0 — внешняя приёмка

1. дождаться green push CI merge-коммита `main`;
2. подтвердить автоматическое обновление целевого сервера;
3. real Telegram smoke: календарь, две культуры, разные даты/фазы, отчёт и risk digest;
4. clean Debian 12 deploy → migrate → start → reboot;
5. intentionally failed release → verified rollback;
6. подтвердить startup calculation сохранённых fields;
7. Astra Linux smoke;
8. message/log/heartbeat/timer evidence;
9. operator runbook для `sending`;
10. screening-only регламент и независимый официальный warning channel.

## P1 — после полевого журнала

### Provider observability

- latency/error/cache/fallback metrics;
- stale-cache age;
- simple circuit breaker;
- admin provider status;
- bounded field concurrency только после метрик.

### Окно полевых работ

- операция выбирается явно;
- осадки, ветер/порывы, температура, RH/VPD и previous rain;
- explanation per constraint;
- отдельное spray weather window без обхода label;
- no opaque suitability score.

### Official warnings

- CAP adapters по стране/региону;
- issuer/identifier/effective/expires/area/severity;
- отдельные секции `официальное предупреждение` и `модельный сигнал`;
- no probability mixing.

### Station verification

- station observation import;
- forecast run ↔ observation matching;
- bias/MAE/RMSE;
- POD/FAR/CSI;
- below-threshold daily evaluations;
- Brier/reliability по risk/lead/season/region.

## P2

1. field polygon geometry;
2. SoilGrids context с uncertainty;
3. Sentinel-2 L2A + SCL/cloud masks;
4. own-field temporal baseline;
5. local FAO-56 при полном наборе входов;
6. validated `Kc/Ks` и root-zone balance;
7. GloFAS/flood screening;
8. pathogen-specific disease models;
9. отдельный hail validation track.

## Технический долг

- вынести weather-risk cycle из `scheduler.py` в application service;
- удалить перехваченные legacy crop/season/report handlers из `handlers/core.py` после отдельного безопасного refactor;
- не использовать `CropSeason.is_active` как долгосрочную модель истории сезонов и выбранного профиля одновременно: перед multi-year season archive ввести отдельный selected-profile marker;
- привести optional RAG к application service/bounded executor/timeouts;
- переименовать `frost_alerts_enabled` в `weather_risk_alerts_enabled`;
- удалить transitional `users` columns после production upgrade evidence;
- постепенно включить mypy и Bandit;
- добавить измерение памяти/latency на целевом слабом сервере;
- не вводить queues/microservices/CQRS без подтверждённой нагрузки.

## Definition of Done следующего релиза

- обновлённый farmer UX автоматически получен целевым сервером;
- real Telegram smoke документирован;
- полевой журнал доступен из production Router graph;
- данные field/crop-scoped и restart-safe;
- full CI/live gates зелёные;
- journal observations не подменяют provider data;
- audit/capability/status/docs синхронизированы.

Пользовательский UX: `docs/FARMER_UX.md`.  
Эксплуатация MVP: `docs/LOW_RESOURCE_MVP.md`.  
Глубокий аудит: `docs/DEEP_AUDIT_2026-07-19.md`.
