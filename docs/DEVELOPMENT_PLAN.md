# План модернизации Crop Forecast Bot

Дата актуализации: **2026-07-11**.

## Целевая архитектура

```text
Telegram / aiogram Router + Redis FSM
        ↓
application services / typed ports
        ↓
domain and scientifically bounded agro calculations
        ↓
infrastructure adapters
  ├─ Open-Meteo forecast / historical reanalysis
  ├─ PostgreSQL repositories / Alembic
  ├─ Redis callback/job leases / deduplication
  └─ optional source-attributed RAG
```

Правила принятия изменений:

1. один Telegram framework и один entrypoint;
2. handlers не выполняют HTTP, расчёты и блокирующий I/O;
3. PostgreSQL — source of truth, Redis — FSM/coordination;
4. observation, reanalysis и forecast не смешиваются;
5. отсутствие данных не заменяется эвристикой или нулём;
6. формула имеет источник, единицы, период и тесты;
7. неподдерживаемая функция явно выключена;
8. state-changing callback задаёт желаемое конечное состояние, а не toggle;
9. релиз принимается после зелёного CI, migration check и runtime smoke;
10. production разворачивается Bash/systemd без Docker.

## Ближайший вертикальный срез — полный Telegram/FSM flow и отказные сценарии

Приоритет: **P0**.

1. Покрыть aiogram flow `field → crop → season → report` сценарными тестами на уровне Router/Dispatcher.
2. Проверить восстановление каждой FSM-ветки после закрытия и повторного открытия RedisStorage.
3. Проверить отказ PostgreSQL и Redis до, во время и после пользовательской операции.
4. Проверить scheduler retry после потери job lease, исключения Telegram API и аварийного завершения worker.
5. Выполнить clean-host `deploy → update → forced failure → rollback → restore` на Debian 12.
6. Выполнить реальный Telegram API smoke для двух полей.

Definition of Done:

- пользовательский flow достигается из `/start` и переживает restart;
- повтор callback не изменяет состояние дважды;
- два scheduler worker не создают двойной alert/digest;
- неуспешная отправка допускает retry, успешная блокируется TTL;
- outage БД/Redis даёт контролируемую ошибку без потери согласованности;
- CI и clean-host smoke воспроизводимы без ручного изменения кода.

## Этап 0 — стабилизация runtime

Статус: **выполнено**.

- [x] aiogram 3.x как единственный Telegram runtime;
- [x] entrypoint `python -m src.bot.main`;
- [x] Router/FSM для поля, культуры, сезона, отчёта и уведомлений;
- [x] удаление глобального пользовательского состояния;
- [x] async DB lifecycle и middleware session;
- [x] typed Open-Meteo contract;
- [x] scheduler session factory;
- [x] graceful startup/shutdown;
- [x] systemd readiness, heartbeat и watchdog;
- [x] native deploy/update/rollback/status.

## Этап 1 — схема и устойчивое состояние

Статус: **production и real-service integration slice выполнены**.

- [x] Alembic baseline и обязательный head;
- [x] adoption legacy `users` schema;
- [x] `Field` и `CropSeason`;
- [x] несколько полей и одно active field;
- [x] отдельные crop/season/phase/preferences;
- [x] Redis FSM;
- [x] Redis scheduler leases;
- [x] persistent notification deduplication;
- [x] snapshot DB targets before external I/O;
- [x] real PostgreSQL migration/repository tests;
- [x] PostgreSQL partial unique indexes и row locking;
- [x] real Redis multi-client lease tests;
- [x] RedisStorage state/data restart test;
- [x] real-service tests в CI без Docker;
- [x] two-worker scheduler lock and notification dedup test on real Redis;
- [ ] failure/restart scheduler orchestration test;
- [ ] cleanup migration legacy user coordinate/crop columns после production verification.

## Этап 2 — научная целостность оперативного отчёта

Статус: **реализован и подтверждён CI; clean-host smoke не выполнен**.

- [x] local-calendar partition текущего дня;
- [x] explicit `reanalysis / operational_past / forecast` labels;
- [x] forecast исключён из completed HTC и P−ET₀;
- [x] NaN не превращается в ложный ноль;
- [x] GDD completed и forecast contributions разделены;
- [x] frost screening использует только forecast rows;
- [x] daily frost data не заявляет точный час события;
- [x] automatic phase inference отключён;
- [x] read-only provider contract smoke;
- [x] capability matrix;
- [x] единый verification script;
- [x] зелёный CI полного среза;
- [ ] clean-host production smoke.

## Этап 3 — provider resilience

Приоритет: **P0/P1**.

- [x] application weather port and domain DTO;
- [x] timeout, retry/backoff, cache and bounded concurrency;
- [x] optional historical extension and explicit degradation;
- [x] cached session shutdown;
- [ ] общий lifecycle для будущих HTTP providers;
- [ ] jittered retry policy;
- [ ] measurable per-provider rate limiter;
- [ ] circuit breaker with half-open probe;
- [ ] stale-cache fallback с возрастом и quality marker;
- [ ] mocked full HTTP contract tests;
- [ ] provider latency/error/fallback metrics.

## Этап 4 — агрометеорологические показатели

### ГДД

- [x] configurable season start;
- [x] crop-specific `Tbase` from one catalogue;
- [x] optional `Tupper` only when explicitly configured;
- [x] completed/forecast separation;
- [x] coverage and missing fraction;
- [x] no automatic phenology;
- [ ] independent crop/region validation;
- [ ] leap year, DST and long-gap integration cases;
- [ ] cultivar/version metadata.

### ГТК

- [x] completed days only;
- [x] `Tmean > 10°C` rule;
- [x] minimum warm-day count;
- [x] missing fraction control;
- [x] no universal moisture classification;
- [ ] season-consistent homogeneous series;
- [ ] vegetation-period continuity rules;
- [ ] regional interpretation backed by sources.

### ET₀ and water status

- [x] ET₀ identified as provider variable;
- [x] paired-data validation;
- [x] no irrigation dose claim;
- [ ] local FAO-56 Penman–Monteith with complete inputs;
- [ ] soil/root-zone storage model;
- [ ] Kc only with validated phase and crop context.

### Frost

- [x] local date and lead in days;
- [x] air 2 m vs plant/surface distinction;
- [x] crop/phase/elevation shown as context;
- [x] no fake probability or exact daily event hour;
- [ ] normative crop/phase damage thresholds;
- [ ] surface temperature provider;
- [ ] terrain/cold-air drainage correction;
- [ ] ensemble uncertainty;
- [ ] POD/FAR/CSI validation dataset.

### SPI and yield

- [x] disabled for short operational data;
- [x] synthetic yield model removed;
- [ ] homogeneous monthly precipitation archive + distribution fit for SPI;
- [ ] real yield dataset, temporal/regional holdout and baseline before any ML release.

## Этап 5 — новые provider domains

Приоритет: **P1/P2**.

- [ ] soil DTO and SoilGrids adapter;
- [ ] ocean/no-data/uncertainty validation;
- [ ] ERA5-Land queued job and cache integrity;
- [ ] satellite DTO and actual provider selection;
- [ ] cloud/quality masks and acquisition metadata;
- [ ] source/version/resolution/fallback metadata in every report;
- [ ] no feature exposed before reachable Telegram flow and tests.

## Этап 6 — Telegram UX and operations

- [x] field → crop → season → report;
- [x] `/start`, `/help`, `/cancel`;
- [x] multi-field management;
- [x] field-level notification switches;
- [x] explicit progress and degraded output;
- [x] distributed callback delivery idempotency;
- [x] rapid double-click semantic suppression;
- [x] desired-state notification callbacks with field context;
- [x] legacy toggle callbacks fail closed;
- [ ] quiet hours and notification windows;
- [ ] archive/delete field flow;
- [ ] admin diagnostics and provider status;
- [ ] full scenario tests with mocked Telegram updates;
- [ ] restart test during each FSM branch.

## Этап 7 — RAG

- [x] optional dependency profile;
- [x] lazy heavy imports;
- [x] runtime feature flag;
- [x] source display;
- [x] fail-closed answer when provider/context is unavailable;
- [ ] document version/date/category metadata;
- [ ] citation validation against retrieved chunks;
- [ ] prompt-injection tests;
- [ ] Russian agronomy evaluation set;
- [ ] hard guard against dose/pesticide advice without normative context.

## Этап 8 — release engineering and observability

- [x] native Bash/systemd release path;
- [x] PostgreSQL backup before update;
- [x] atomic symlink activation and code rollback;
- [x] verification command and live provider smoke;
- [x] real PostgreSQL/Redis CI without Docker;
- [ ] `uv.lock` validated on Debian/Astra;
- [ ] clean-host Debian 12 test;
- [ ] Astra Linux test;
- [ ] automated failed-start rollback test;
- [ ] periodic restore verification;
- [ ] JSON logs and correlation ID;
- [ ] provider/scheduler metrics;
- [ ] release tags and signed/verified source policy.

## Definition of Done ближайшего релиза

- [x] CI зелёный для всего `src/config/alembic/tests`;
- [x] real PostgreSQL/Redis integration tests;
- [x] callback and scheduler worker idempotency tests;
- [x] Open-Meteo live smoke available;
- [ ] two-field Telegram smoke проходит после deployment;
- [ ] Alembic head подтверждён на production-копии;
- [ ] deploy/update/rollback проверены на чистом Debian 12;
- [x] отсутствуют legacy entrypoints, Docker scripts и synthetic models;
- [x] README, capability matrix, status и changelog совпадают с runtime;
- [x] все недоступные научные функции явно выключены.
