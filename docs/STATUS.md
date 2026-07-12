# Статус разработки

Дата актуализации: **2026-07-12**.

Текущий `main`: **PR #27 слит**, squash-коммит `4c87e9b`. Production-агроотчёт содержит однородное сравнение текущего сезона ERA5-Land с фиксированной базой ERA5-Land 1991–2020.

## Production-контур

```text
aiogram 3.x
PostgreSQL + Alembic
Redis FSM / callback idempotency / renewable leases / deduplication
Open-Meteo Forecast + bounded Historical Weather
ERA5-Land current season + 1991–2020 reference via Open-Meteo
APScheduler
systemd + Bash release scripts
```

## Выполнено

### Runtime, Telegram и состояние

- [x] один entrypoint `python -m src.bot.main`;
- [x] native deploy/update/rollback/status без Docker;
- [x] graceful startup/shutdown, readiness, heartbeat и watchdog;
- [x] несколько полей, культура, дата сезона и ручная фаза;
- [x] отдельные настройки уведомлений каждого поля;
- [x] Redis FSM restart;
- [x] callback delivery idempotency и rapid double-click suppression;
- [x] desired-state callbacks вместо toggle;
- [x] race-safe onboarding через PostgreSQL upsert и row lock;
- [x] полный Dispatcher-flow `field → crop → season → phase → report`;
- [x] controlled PostgreSQL/Redis/Telegram error UX.

### PostgreSQL и Redis coordination

- [x] Alembic baseline и обязательный head;
- [x] `Field` / `CropSeason` и несколько полей;
- [x] row locks для user/field/season mutations;
- [x] пользователь, поле и сезон создаются в одной транзакции;
- [x] failure-injection после `flush`, но до `COMMIT`, не оставляет частичных записей;
- [x] renewable Redis scheduler leases;
- [x] отмена текущего read/report после lease loss;
- [x] crash/TTL recovery и two-worker tests;
- [x] field/day/event notification deduplication.

### Оперативные и накопленные показатели

- [x] typed weather DTO и async provider port;
- [x] раздельные `reanalysis / operational_past / forecast`;
- [x] текущий локальный день не считается завершённым прошлым;
- [x] ГДД строго от локальной даты начала сезона;
- [x] ГТК без прогнозных осадков;
- [x] P−ET₀ без подстановки нулей;
- [x] накопленные `P` и provider `ET₀`;
- [x] `ΣP−ΣET₀` только по парным валидным суткам;
- [x] ETCCDI dry/wet threshold `1 мм/сут`;
- [x] текущая и максимальная сухая серия на непрерывном ряду;
- [x] максимумы осадков за 1 и 5 последовательных суток;
- [x] отрицательные значения и прогноз не искажают накопления.

### Однородное ERA5-Land сравнение — PR #27

- [x] typed climate DTO и async provider port;
- [x] раздельные `current_daily` и `reference_daily`;
- [x] одна модель `models=era5_land` для текущего сезона и 1991–2020;
- [x] оперативные Best Match/Forecast значения не входят в климатические аномалии;
- [x] текущий cache 6 часов, reference cache 30 суток;
- [x] полностью пустой хвост задержанного ERA5-Land удаляется;
- [x] фактическая дата окончания климатического ряда показывается пользователю;
- [x] same-length windows с той же календарной датой старта;
- [x] минимум 20 валидных reference-лет;
- [x] empirical mid-rank percentiles без distribution fit;
- [x] mean/median/P10/P25/P75/P90;
- [x] средняя температура, осадки, provider ET₀, crop-specific ГДД и сухие серии;
- [x] накопленные climate-метрики fail-closed при любом пропуске;
- [x] температура в °C сравнивается аддитивно, без `% от среднего`;
- [x] 29 февраля не сдвигается на соседнюю дату;
- [x] outage climate provider не блокирует основной отчёт;
- [x] Telegram-отчёт укладывается в 4096 символов;
- [x] результат не называется station normal, probability, SPI или SPEI.

### QA

PR #27 прошёл:

- [x] Ruff и `compileall`;
- [x] Bash syntax и ShellCheck;
- [x] repository legacy policy;
- [x] scientific-claims policy;
- [x] unit и contract tests;
- [x] реальные PostgreSQL/Redis integration tests;
- [x] Alembic graph.

## Текущий этап — P0 clean-host release gate

- [ ] физический PostgreSQL disconnect во время `COMMIT` на отдельном процессе/сервере;
- [ ] Redis loss после получения callback lease;
- [ ] неоднозначный Telegram result между внешней отправкой и dedup commit;
- [ ] конкурентное редактирование исходного Telegram-сообщения;
- [ ] `deploy → reboot → update → forced failure → rollback` на Debian 12;
- [ ] восстановление PostgreSQL dump в отдельную БД;
- [ ] реальный Telegram API smoke для двух полей;
- [ ] live smoke Forecast/Historical/ERA5-Land на контрольных точках;
- [ ] smoke на поддерживаемом Astra Linux окружении.

> Telegram Bot API не предоставляет application idempotency key для `sendMessage`. Абсолютный exactly-once результат между внешней отправкой и Redis dedup недоказуем; бот не должен быть единственным каналом критических предупреждений.

## Следующие этапы

### P1 — provider resilience

- [ ] mocked full operational HTTP contract;
- [ ] jittered retry и circuit breaker;
- [ ] измеримый rate limiter;
- [ ] stale-cache fallback с возрастом данных;
- [ ] provider latency/error/fallback metrics;
- [ ] отдельная телеметрия больших climate-запросов;
- [ ] прямой CDS/ERA5-Land queued job/object-cache pipeline.

### P1 — научная валидация

- [ ] versioned sources для `Tbase/Tupper`;
- [ ] crop/region/cultivar validation;
- [ ] региональная фенология с uncertainty;
- [ ] frost thresholds по культуре и фазе;
- [ ] surface temperature, terrain и ensemble inputs;
- [ ] homogeneous continuity rules для ГТК;
- [ ] local FAO-56 при полном наборе входов;
- [ ] сравнение осадков/ET₀ и ERA5-Land с локальными станциями;
- [ ] SPI/SPEI только после отдельного validated distribution pipeline.

### P1/P2 — новые данные и UX

- [ ] SoilGrids adapter и ocean/no-data validation;
- [ ] Sentinel-2/MODIS provider с quality masks;
- [ ] provenance/version/resolution для каждого показателя;
- [ ] синхронизировать одну строку `/help` о назначении даты сезона;
- [ ] field archive/delete и user data export/delete;
- [ ] quiet hours и configurable delivery window;
- [ ] administrative provider status.

## Критерий полевого пилота

- [x] реальные данные без синтетического fallback;
- [x] явная деградация качества;
- [x] race-safe PostgreSQL/Redis contracts;
- [x] scheduler lease heartbeat и crash recovery;
- [x] pre-commit rollback;
- [x] водные накопления с единицами, периодом, provenance и QC;
- [x] homogeneous ERA5-Land current/reference comparison с QC и Telegram tests;
- [ ] clean-host deployment;
- [ ] реальный Telegram smoke;
- [ ] live provider control points;
- [ ] параллельная проверка с локальной станцией;
- [ ] эксплуатационные метрики и утверждённый screening-only регламент.
