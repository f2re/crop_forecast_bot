# План модернизации Crop Forecast Bot

Дата актуализации: **2026-07-12**.

## Целевая архитектура

```text
Telegram / aiogram Router + Redis FSM
        ↓
application services / typed ports
        ↓
domain / scientifically bounded calculations
        ↓
infrastructure adapters
  ├─ Open-Meteo forecast / historical reanalysis
  ├─ PostgreSQL repositories / Alembic
  ├─ Redis callback/job leases / deduplication
  └─ optional source-attributed RAG
```

## Правила принятия изменений

1. Один Telegram framework и один entrypoint.
2. Handlers не выполняют расчёты, HTTP и блокирующий I/O.
3. PostgreSQL — source of truth; Redis — FSM и coordination.
4. Observation, reanalysis и forecast не смешиваются.
5. Отсутствие данных не заменяется эвристикой или нулём.
6. Формула имеет источник, единицы, период и тесты.
7. Неподдерживаемая функция явно выключена.
8. State-changing callback задаёт конечное состояние, а не toggle.
9. Background monitoring относится ко всем enabled fields.
10. Релиз принимается после CI, migration check и runtime smoke.
11. Production разворачивается Bash/systemd без Docker.

## Активный вертикальный срез — field-readiness

Приоритет: **P0**.

### Выполнено в текущем срезе

- [x] различить `insufficient_forecast_data` и подтверждённое `no_risk`;
- [x] запретить зелёный frost-вывод при отсутствии валидной Tmin;
- [x] фильтровать ГДД строго от локальной даты начала сезона;
- [x] требовать строку на дату старта для заявления сезонной суммы;
- [x] мониторить все поля с enabled notification flag;
- [x] отправлять дайджест в локальном утреннем окне поля;
- [x] сделать создание пользователя dialect-aware upsert;
- [x] сериализовать первичное создание поля row lock;
- [x] добавить model/retrieval/cache provenance;
- [x] расширить unit и PostgreSQL integration tests;
- [x] актуализировать README, status и capability matrix.

### Definition of Done среза

- [x] Ruff, compileall, unit и integration tests зелёные;
- [x] PostgreSQL concurrent onboarding test зелёный;
- [x] все enabled fields присутствуют в scheduler targets;
- [x] report test запрещает false no-risk;
- [ ] live Open-Meteo smoke подтверждает provenance текущего release;
- [ ] PR слит после зелёного CI.

## Этап 0 — runtime

Статус: **выполнено**.

- [x] aiogram 3.x и `python -m src.bot.main`;
- [x] Router/FSM основного пользовательского пути;
- [x] graceful startup/shutdown;
- [x] systemd readiness, heartbeat и watchdog;
- [x] native deploy/update/rollback/status;
- [x] callback idempotency;
- [x] distributed scheduler locks.

## Этап 1 — PostgreSQL и Redis

Статус: **production + real-service integration выполнены**.

- [x] Alembic baseline и обязательный head;
- [x] adoption legacy schema;
- [x] `Field` и `CropSeason`;
- [x] несколько полей;
- [x] Redis FSM restart test;
- [x] PostgreSQL partial unique indexes;
- [x] row locking активного поля;
- [x] multi-client Redis lease tests;
- [x] two-worker alert/digest tests;
- [x] race-safe user onboarding;
- [ ] cleanup migration legacy user coordinates/crop columns после production-проверки.

## Этап 2 — научная целостность

Статус: **основной screening layer реализован**.

### ГДД

- [x] crop-specific `Tbase` из одного каталога;
- [x] optional `Tupper` только при явной настройке;
- [x] completed/forecast separation;
- [x] local-date season boundary;
- [x] coverage и missing fraction;
- [x] no automatic phenology;
- [ ] independent crop/region/cultivar validation;
- [ ] versioned parameter sources;
- [ ] leap year, DST и long-gap scenario suite.

### ГТК

- [x] completed days only;
- [x] `Tmean > 10°C`;
- [x] minimum warm-day count;
- [x] missing fraction control;
- [x] no universal classification;
- [ ] season-consistent homogeneous series;
- [ ] vegetation-period continuity rules;
- [ ] regional interpretation sources.

### ET₀ и водный статус

- [x] ET₀ обозначен как provider variable;
- [x] paired-data validation;
- [x] no irrigation-dose claim;
- [ ] local FAO-56 Penman–Monteith с полным набором входов;
- [ ] soil/root-zone storage model;
- [ ] Kc только с валидированной фазой.

### Заморозки

- [x] forecast rows only;
- [x] air 2 m vs plant/surface distinction;
- [x] explicit insufficient-data state;
- [x] no fake probability or exact event hour;
- [ ] normative crop/phase damage thresholds;
- [ ] surface temperature provider;
- [ ] terrain/cold-air drainage correction;
- [ ] ensemble uncertainty;
- [ ] POD/FAR/CSI validation dataset.

## Этап 3 — provider resilience

Приоритет: **P1**.

- [x] typed weather port/DTO;
- [x] timeout, retry, cache и bounded concurrency;
- [x] controlled historical fallback;
- [x] provider resource shutdown;
- [x] retrieval/cache provenance;
- [ ] mocked full HTTP contract;
- [ ] jittered retry и circuit breaker;
- [ ] measurable rate limiter;
- [ ] stale-cache age/quality marker;
- [ ] provider metrics;
- [ ] actual model-run/grid metadata from supporting endpoints.

## Этап 4 — Telegram/FSM failure scenarios

Приоритет: **P0**.

- [ ] полный Dispatcher test `field → crop → season → report`;
- [ ] restart каждой FSM-ветки;
- [ ] PostgreSQL outage during operation;
- [ ] Redis outage during callback/FSM;
- [ ] callback после удаления/редактирования сообщения;
- [ ] worker crash и потеря scheduler lease;
- [ ] field archive/delete flow;
- [ ] quiet hours и configurable delivery window.

## Этап 5 — новые данные

Приоритет: **P1/P2**.

- [ ] SoilGrids DTO/adapter и ocean/no-data validation;
- [ ] ERA5-Land asynchronous job/cache pipeline;
- [ ] Sentinel-2/MODIS provider с quality masks;
- [ ] provenance/version/resolution для каждого показателя;
- [ ] ни одна функция не появляется в UI до тестируемого vertical slice.

## Этап 6 — RAG

- [x] optional dependency profile;
- [x] lazy initialization;
- [x] feature flag и source display;
- [x] fail-closed response;
- [ ] document version/date/category metadata;
- [ ] citation-to-chunk validation;
- [ ] prompt-injection tests;
- [ ] Russian agronomy evaluation set;
- [ ] hard guard для доз/препаратов.

## Этап 7 — release engineering и наблюдаемость

- [x] Bash/systemd releases;
- [x] PostgreSQL backup перед update;
- [x] atomic activation и code rollback;
- [x] verification script и live provider smoke;
- [x] real PostgreSQL/Redis CI без Docker;
- [ ] `uv.lock` на целевых ОС;
- [ ] clean-host Debian 12 test;
- [ ] Astra Linux test;
- [ ] automated failed-start rollback;
- [ ] periodic restore verification;
- [ ] JSON logs и correlation ID;
- [ ] provider/scheduler/Telegram metrics;
- [ ] signed release source policy.

## Definition of Done полевого пилота

- [ ] текущий field-readiness PR слит с зелёным CI;
- [ ] clean-host deploy/update/rollback пройден;
- [ ] реальный Telegram smoke для двух полей пройден;
- [ ] Open-Meteo live smoke пройден на контрольных точках;
- [ ] параллельное сравнение с локальной станцией выполнено;
- [ ] регламент эксплуатации утверждает screening-only статус;
- [ ] критичные предупреждения имеют независимый резервный канал.
