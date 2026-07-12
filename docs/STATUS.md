# Статус разработки

Дата актуализации: **2026-07-12**.

Текущий `main` перед этим срезом: PR #26 с накопленными осадками, provider ET₀ и показателями непрерывности осадков. В текущем срезе production-отчёт дополнен сезонным сравнением с фиксированной реанализной базой ERA5-Land 1991–2020.

## Текущий production-контур

```text
aiogram 3.x
PostgreSQL + Alembic
Redis FSM / callback idempotency / renewable leases / deduplication
Open-Meteo Forecast + Historical Weather
ERA5-Land 1991–2020 reference via Open-Meteo
APScheduler
systemd + Bash release scripts
```

## Выполнено

### Runtime и эксплуатация

- [x] один entrypoint `python -m src.bot.main`;
- [x] native deploy/update/rollback/status без Docker;
- [x] systemd readiness, heartbeat и watchdog;
- [x] atomic releases и PostgreSQL backup;
- [x] обязательный Alembic head на startup;
- [x] полный CI для `src/config/alembic/tests`;
- [x] реальные PostgreSQL и Redis в CI.

### Telegram и состояние

- [x] несколько полей;
- [x] геолокация и ручные координаты;
- [x] культура, дата сезона и ручная фаза;
- [x] отдельные настройки уведомлений каждого поля;
- [x] Redis FSM restart;
- [x] callback delivery idempotency;
- [x] подавление rapid double-click;
- [x] desired-state callback вместо toggle;
- [x] race-safe создание пользователя через upsert;
- [x] первичное создание поля под row lock;
- [x] полный Dispatcher-flow `field → crop → season → phase → report`;
- [x] выбор ручной фазы использует единый каталог фаз;
- [x] основные FSM-ветки продолжаются после повторного открытия RedisStorage;
- [x] ошибки PostgreSQL/Redis преобразуются в контролируемые сообщения;
- [x] удалённое Telegram-сообщение открывает актуальное меню.

### Транзакционная целостность PostgreSQL

- [x] state-changing операции больше не выполняют промежуточный commit внутри `_lock_user`;
- [x] пользователь, поле и сезон создаются в одной транзакции;
- [x] изменение культуры, даты сезона и ручной фазы блокирует строку пользователя;
- [x] failure-injection после `flush`, но до `COMMIT`, откатывает пользователя, поле и сезон целиком;
- [x] конкурентный onboarding создаёт одного пользователя, одно поле и один сезон.

### Источники и расчёты

- [x] typed weather DTO и provider port;
- [x] typed climate DTO и отдельный async climate provider port;
- [x] раздельные `reanalysis / operational_past / forecast`;
- [x] текущий локальный день не считается завершённым прошлым;
- [x] ГДД строго от локальной даты начала сезона;
- [x] ГТК без прогнозных осадков;
- [x] P−ET₀ без подстановки нулей;
- [x] накопленные `P` и provider `ET₀` за сезон/доступный завершённый период;
- [x] накопленная `ΣP−ΣET₀` только по парным валидным суткам;
- [x] сухие/влажные сутки по порогу ETCCDI `1 мм/сут`;
- [x] текущая и максимальная сухая серия только на непрерывном ряду;
- [x] максимум осадков за 1 и 5 последовательных суток;
- [x] отрицательные значения и прогнозные строки не искажают накопления;
- [x] фиксированная ERA5-Land база 1991–2020, а не смешанный `Best Match`;
- [x] одинаковые по длине сезонные окна с той же календарной датой старта;
- [x] минимум 20 валидных референсных лет;
- [x] эмпирические процентили без normal/gamma distribution fit;
- [x] аддитивная температурная аномалия без физически некорректного `% от °C`;
- [x] накопленные климатические метрики fail-closed при любом пропуске;
- [x] 29 февраля не сдвигается на соседнюю дату;
- [x] climate-provider outage не блокирует основной агроотчёт;
- [x] frost screening только по прогнозным строкам;
- [x] `insufficient_forecast_data` отделён от `no_risk`;
- [x] fail-closed предупреждение при недоступной Tmin;
- [x] модельная конфигурация, время получения и cache policy в metadata;
- [x] неподдерживаемые научные функции выключены.

### Scheduler и Redis coordination

- [x] distributed job locks;
- [x] автоматическое продление job lease независимо от итерации по полям;
- [x] долгий provider/report вызов может превышать исходный TTL без запуска второго worker;
- [x] потеря token ownership отменяет текущий read/report и запрещает новые side effects;
- [x] worker, завершившийся без release, освобождает lock по TTL;
- [x] следующий worker выполняет безопасный retry после восстановления ownership;
- [x] field/day/event deduplication;
- [x] два worker не дублируют alert/digest;
- [x] retry после неуспешной Telegram-отправки;
- [x] фоновые задания охватывают все включённые поля;
- [x] ежедневный отчёт проверяется в локальном утреннем окне поля;
- [x] предупреждение о недоступной Tmin дедуплицируется по полю и дате.

## Текущий этап

### P0 — clean-host и остаточные аварийные сценарии

- [ ] физический PostgreSQL disconnect во время `COMMIT` на отдельном процессе/сервере;
- [ ] Redis loss после получения callback lease;
- [ ] неопределённый результат: процесс погиб после принятия сообщения Telegram, но до фиксации dedup lease;
- [ ] конкурентное редактирование исходного Telegram-сообщения;
- [ ] `deploy → update → forced failure → rollback` на Debian 12;
- [ ] восстановление PostgreSQL dump в отдельную БД;
- [ ] реальный Telegram API smoke для двух полей;
- [ ] live smoke полного 1991–2020 ERA5-Land запроса на контрольных точках;
- [ ] smoke на поддерживаемом Astra Linux окружении.

> Telegram Bot API не предоставляет idempotency key для `sendMessage`. Поэтому абсолютный exactly-once результат при гибели процесса между внешней отправкой и фиксацией Redis dedup недоказуем. Текущий контракт: lease до отправки, дедупликация после подтверждённого успеха и контролируемый retry при явной ошибке.

## Следующие этапы

### P1 — provider resilience

- [ ] mocked full HTTP contract Open-Meteo;
- [ ] jittered retry и circuit breaker;
- [ ] измеримый rate limit;
- [ ] stale-cache fallback с возрастом данных;
- [ ] provider latency/error/fallback metrics;
- [ ] отдельная телеметрия больших climate-reference запросов;
- [ ] model-run и grid metadata через provider, который их реально отдаёт.

### P1 — научная валидация

- [ ] источники и версии `Tbase/Tupper`;
- [ ] crop/region/cultivar validation;
- [ ] региональная фенология с uncertainty;
- [ ] frost thresholds по культуре и фазе;
- [ ] surface temperature, terrain и ensemble inputs;
- [ ] сезонный ряд и правила непрерывности для ГТК;
- [ ] локальный FAO-56 только после полного набора входов;
- [ ] сравнение осадков и provider ET₀ с полевой станцией/лизиметром;
- [ ] bias assessment ERA5-Land по регионам и сезонам;
- [ ] SPI/SPEI только после отдельного длинного однородного pipeline и distribution fit.

### P1/P2 — новые данные

- [ ] SoilGrids adapter и ocean/no-data validation;
- [ ] прямая CDS/ERA5-Land queued job/object-cache pipeline;
- [ ] Sentinel-2/MODIS provider с quality masks;
- [ ] provenance/version/resolution для каждого показателя.

## Критерий полевого пилота

- [x] реальные данные без синтетического fallback;
- [x] явная деградация качества;
- [x] все включённые поля мониторятся;
- [x] race-safe PostgreSQL/Redis contracts;
- [x] scheduler lease heartbeat и crash recovery подтверждены реальным Redis;
- [x] pre-commit rollback подтверждён реальным PostgreSQL;
- [x] накопленные водные показатели имеют единицы, период, provenance и QC;
- [x] реанализное сравнение имеет фиксированный период, одинаковые окна, QC и Telegram tests;
- [ ] clean-host deployment;
- [ ] реальный Telegram smoke;
- [ ] параллельная проверка с локальной метеостанцией;
- [ ] журнал ошибок и метрики эксплуатации;
- [ ] утверждённый регламент: бот — screening, не автономное решение.
