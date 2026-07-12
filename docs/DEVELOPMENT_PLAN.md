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
10. Пользовательская state-changing операция не имеет промежуточных commit.
11. Worker не продолжает side effects после потери lease ownership.
12. Релиз принимается после CI, migration check и runtime smoke.
13. Production разворачивается Bash/systemd без Docker.
14. Накопления строятся только по завершённым локальным суткам и сохраняют provenance.
15. Разность двух величин вычисляется по одному и тому же набору парных наблюдений.

## Завершённый срез — field-readiness

Статус: **слит через PR #21**.

- [x] `insufficient_forecast_data` отделён от подтверждённого `no_risk`;
- [x] ГДД фильтруются строго от локальной даты начала сезона;
- [x] все enabled fields мониторятся в фоне;
- [x] daily digest использует локальное утреннее окно поля;
- [x] race-safe onboarding через upsert и row lock;
- [x] provider provenance и regression tests.

## Завершённый срез — Telegram/FSM reliability

Статус: **слит через PR #24**.

- [x] testable production `build_dispatcher`;
- [x] Dispatcher-flow `field → crop → season → phase → report`;
- [x] RedisStorage reopen для основных FSM-веток;
- [x] controlled PostgreSQL/Redis error UX;
- [x] deleted-message callback recovery;
- [x] единый каталог ручных фаз;
- [x] UX all-field monitoring синхронизирован с scheduler.

## Завершённый срез — process failure orchestration

Статус: **реализован и подтверждён полным CI в PR #25**.

- [x] reusable `RenewingLease` с token-checked heartbeat;
- [x] продление scheduler lock во время долгого provider/report I/O;
- [x] отмена текущего read/report после потери ownership;
- [x] запрет перехода к следующему полю после lease loss;
- [x] реальный Redis test: job дольше исходного TTL не запускает второй worker;
- [x] реальный Redis test: принудительное удаление lock отменяет job и разрешает retry другому worker;
- [x] subprocess crash без release и восстановление lock после TTL;
- [x] `_lock_user` больше не вызывает промежуточный commit;
- [x] crop/season/phase mutations выполняются под user row lock;
- [x] real PostgreSQL failure-injection после `flush` и до `COMMIT`;
- [x] rollback оставляет ноль частичных user/field/season записей;
- [x] caller cancellation не оставляет защищённую coroutine работающей в фоне.

Ограничение: per-notification Redis reservation снижает риск дубля, но Telegram `sendMessage` не имеет idempotency key. Если процесс погиб после принятия сообщения Telegram и до фиксации dedup lease, результат внешней отправки остаётся неопределённым. Это должно учитываться в эксплуатационном регламенте.

## Завершённый срез — накопленные осадки и атмосферная испаряемость

Статус: **реализован в production agro-report и покрыт unit/application tests**.

- [x] накопленная сумма осадков по завершённым локальным суткам;
- [x] накопленная provider ET₀ с независимым контролем полноты;
- [x] `ΣP−ΣET₀` только по парным валидным суткам;
- [x] сезонная граница по локальной дате посева/начала сезона;
- [x] прогнозные строки исключены из накоплений;
- [x] отрицательные значения не превращаются в ноль;
- [x] сухой день `P < 1 мм/сут` и влажный день `P ≥ 1 мм/сут` по ETCCDI/Climdex;
- [x] текущая и максимальная сухая серия только на непрерывном ряду;
- [x] максимум осадков за 1 и 5 последовательных суток;
- [x] overlap forecast/completed одной даты не скрывает завершённую строку;
- [x] источник, период, число валидных суток и ограничения отображаются в отчёте;
- [x] показатели не называются влагозапасом, фактической ET культуры или дозой полива.

Методическая спецификация: `docs/SCIENTIFIC_WATER_INDICATORS.md`.

## Активный вертикальный срез — clean-host release gate

Приоритет: **P0**.

1. Чистая Debian 12 VM: `deploy.sh` без ручной правки кода.
2. Reboot и подтверждение автоматического systemd startup.
3. Реальный Telegram smoke для двух полей.
4. `update.sh` на новый release.
5. Намеренно повреждённый release и healthcheck failure.
6. Автоматический возврат предыдущего кода и systemd unit.
7. `pg_restore` последнего dump в отдельную test database.
8. Сравнение пользователей, полей, сезонов и Alembic revision.
9. Повторение smoke на поддерживаемом Astra Linux окружении.

Definition of Done:

- deploy/update/rollback воспроизводимы только документированными командами;
- service восстанавливается после reboot;
- failed release не остаётся активным;
- backup реально восстанавливается;
- Telegram flow работает до и после rollback;
- status/doctor отражают фактическое состояние.

## Остаточные P0 failure scenarios

- [ ] физический разрыв PostgreSQL-соединения во время `COMMIT`;
- [ ] Redis outage после получения callback lease;
- [ ] crash после принятия Telegram-сообщения и до dedup commit;
- [ ] конкурентное редактирование Telegram-сообщения;
- [ ] operator runbook для неоднозначного внешнего результата.

## Этап 0 — runtime

Статус: **выполнено**.

- [x] aiogram 3.x и `python -m src.bot.main`;
- [x] Router/FSM основного пути;
- [x] graceful startup/shutdown;
- [x] systemd readiness, heartbeat и watchdog;
- [x] native deploy/update/rollback/status;
- [x] callback idempotency;
- [x] distributed renewable scheduler locks.

## Этап 1 — PostgreSQL и Redis

Статус: **production + real-service integration выполнены**.

- [x] Alembic baseline и обязательный head;
- [x] adoption legacy schema;
- [x] `Field` и `CropSeason`;
- [x] несколько полей;
- [x] Redis FSM restart;
- [x] PostgreSQL partial unique indexes;
- [x] row locking active field/user mutations;
- [x] multi-client Redis leases;
- [x] two-worker alert/digest tests;
- [x] race-safe onboarding;
- [x] atomic pre-commit rollback test;
- [x] crash/TTL lease recovery test;
- [ ] cleanup migration legacy user coordinate/crop columns после production-проверки.

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
- [ ] leap year, DST и long-gap suite.

### ГТК

- [x] completed days only;
- [x] `Tmean > 10°C`;
- [x] minimum warm-day count;
- [x] missing fraction control;
- [x] no universal classification;
- [ ] season-consistent homogeneous series;
- [ ] vegetation-period continuity rules;
- [ ] regional interpretation sources.

### ET₀, осадки и водный статус

- [x] ET₀ обозначен как provider variable;
- [x] paired-data validation;
- [x] no irrigation-dose claim;
- [x] накопленные `P` и provider `ET₀` по завершённым локальным суткам;
- [x] сезонная `ΣP−ΣET₀` только по парным валидным суткам;
- [x] ETCCDI-compatible dry/wet threshold и bounded-period spell metrics;
- [x] Rx1day/Rx5day operation с continuity guard;
- [x] отрицательные значения и пропуски fail-closed;
- [ ] полевая валидация осадков и ET₀ по станции/лизиметру;
- [ ] local FAO-56 Penman–Monteith с полным набором входов;
- [ ] soil/root-zone storage model;
- [ ] Kc только с валидированной фазой;
- [ ] SPI/SPEI только на длинном однородном ряду и климатической норме.

### Заморозки

- [x] forecast rows only;
- [x] air 2 m vs plant/surface distinction;
- [x] explicit insufficient-data state;
- [x] fail-closed unavailable-data notification;
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

## Этап 4 — UX и lifecycle данных

- [x] полный Dispatcher test;
- [x] restart основных FSM-веток;
- [x] fail-closed dependency error UX;
- [ ] field archive/delete flow;
- [ ] user data export/delete;
- [ ] quiet hours и configurable delivery window;
- [ ] administrative provider status.

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
- [x] verification script и live provider smoke command;
- [x] real PostgreSQL/Redis CI без Docker;
- [ ] `uv.lock` на целевых ОС;
- [ ] clean-host Debian 12 test;
- [ ] Astra Linux test;
- [ ] automated failed-start rollback test;
- [ ] periodic restore verification;
- [ ] JSON logs и correlation ID во всех слоях;
- [ ] provider/scheduler/Telegram metrics;
- [ ] signed release source policy.

## Definition of Done полевого пилота

- [x] field-readiness и Telegram/FSM reliability слиты с зелёным CI;
- [x] scheduler heartbeat/loss и transaction rollback проверены реальными сервисами;
- [x] накопленные показатели осадков/ET₀ имеют источники, единицы, QC и Telegram tests;
- [ ] clean-host deploy/update/rollback пройден;
- [ ] реальный Telegram smoke для двух полей пройден;
- [ ] Open-Meteo live smoke пройден на контрольных точках;
- [ ] параллельное сравнение с локальной станцией выполнено;
- [ ] регламент эксплуатации утверждает screening-only статус;
- [ ] критичные предупреждения имеют независимый резервный канал.
