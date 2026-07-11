# Статус разработки

Дата актуализации: **2026-07-11**.

## Текущий production-контур

```text
aiogram 3.x
PostgreSQL + Alembic
Redis FSM / callback idempotency / scheduler leases / deduplication
Open-Meteo Forecast + Historical Weather
APScheduler
systemd + Bash release scripts
```

## Выполнено

### Runtime и эксплуатация

- [x] один aiogram-entrypoint `python -m src.bot.main`;
- [x] удалён telebot runtime;
- [x] нативные `deploy/update/rollback/status` без Docker;
- [x] systemd readiness, heartbeat и watchdog;
- [x] atomic release directories и PostgreSQL backup;
- [x] обязательный Alembic head на startup;
- [x] production verification script;
- [x] полный CI для `src/config/alembic/tests`.

### Пользовательский flow

- [x] несколько полей;
- [x] геолокация и ручные координаты;
- [x] культура, дата сезона и ручная фаза;
- [x] отдельные настройки уведомлений;
- [x] отчёт из реального Telegram-сценария;
- [x] `/start`, `/help`, `/cancel`;
- [x] exact callback redelivery не выполняет handler повторно;
- [x] быстрые повторные нажатия подавляются общим Redis coordination;
- [x] уведомления используют desired-state callback вместо неидемпотентного toggle;
- [x] callback старого или другого поля отклоняется без изменения данных.

### Данные и расчёты

- [x] typed weather DTO и provider port;
- [x] раздельные reanalysis / operational past / forecast;
- [x] локальный календарный день в классификации данных;
- [x] ГДД с `Tbase`, покрытием и пропусками;
- [x] ГТК без прогнозных осадков;
- [x] P−ET₀ без подстановки нулей;
- [x] frost screening только по прогнозным строкам;
- [x] явные scientific limitations;
- [x] read-only live provider smoke.

### PostgreSQL и Redis integration

- [x] Alembic `upgrade head` на реальном PostgreSQL;
- [x] adoption и backfill legacy `users` schema;
- [x] PostgreSQL partial unique indexes active field/season;
- [x] конкурентное переключение active field под row lock;
- [x] field-level scheduler target filters на PostgreSQL;
- [x] атомарные Redis leases между независимыми клиентами;
- [x] token-checked renew/release на реальном Redis;
- [x] межклиентская дедупликация `_send_once`;
- [x] восстановление aiogram FSM state/data после повторного открытия RedisStorage;
- [x] два runtime worker конкурируют за один callback action key;
- [x] два scheduler worker с реальным Redis отправляют один frost alert;
- [x] повтор scheduler job после освобождения job lock не дублирует alert;
- [x] CI запускает PostgreSQL и Redis системными сервисами, без Docker.

### Очистка репозитория

- [x] удалена синтетическая Random Forest training pipeline;
- [x] удалены недостижимые Docker/legacy entrypoints;
- [x] удалены неподключённые эвристические climate/soil/satellite modules;
- [x] core и RAG зависимости разделены;
- [x] добавлена capability matrix.

## Выполняемый этап

### P0 — полные Telegram/FSM и отказные сценарии

- [ ] сценарный test полного field → crop → season → report flow;
- [ ] повтор scheduler job после потери lease/аварийного завершения worker;
- [ ] недоступность PostgreSQL во время активного FSM;
- [ ] недоступность Redis во время callback/FSM;
- [ ] реальный Telegram API smoke после deployment;
- [ ] проверка callback после редактирования или удаления исходного сообщения.

### P0 — clean-host эксплуатация

- [ ] deploy/update/rollback на чистой Debian 12 VM;
- [ ] failed-start rollback test;
- [ ] restore PostgreSQL dump в отдельную БД;
- [ ] smoke на поддерживаемом Astra Linux окружении.

## Следующие этапы

### P1 — provider resilience

- [ ] mocked full HTTP contract Open-Meteo;
- [ ] общий lifecycle HTTP-клиентов;
- [ ] circuit breaker и измеримый rate limit;
- [ ] structured provider metadata и latency/error metrics;
- [ ] контролируемый stale-cache fallback с возрастом данных.

### P1 — научный слой

- [ ] независимая валидация `Tbase/Tupper` по культуре и региону;
- [ ] региональная фенология с uncertainty;
- [ ] frost thresholds по культуре/фазе с нормативными источниками;
- [ ] surface-temperature/terrain/ensemble inputs;
- [ ] сезонный ряд для ГТК с правилами непрерывности;
- [ ] локальный FAO-56 только после полного набора входов.

### P1/P2 — новые данные

- [ ] SoilGrids adapter + ocean/no-data validation;
- [ ] ERA5-Land asynchronous job/cache pipeline;
- [ ] Sentinel-2/MODIS provider после проверки доступа и квот;
- [ ] metadata provenance для каждого показателя.

## Критерий ближайшего релиза

- [x] зелёный CI полного дерева;
- [x] live Open-Meteo smoke;
- [x] реальные PostgreSQL/Redis integration tests;
- [x] callback idempotency и desired-state notification controls;
- [x] двухворкерная Redis-защита scheduler;
- [x] отсутствие legacy/fake runtime;
- [x] явное отключение неподдерживаемых возможностей;
- [ ] clean-host systemd deployment;
- [ ] проверенный Telegram flow для двух полей после deployment;
- [ ] проверенный rollback и восстановление БД.
