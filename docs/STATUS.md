# Статус разработки

Дата актуализации: **2026-07-10**.

## Текущий production-контур

```text
aiogram 3.x
PostgreSQL + Alembic
Redis FSM / leases / deduplication
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
- [x] production verification script.

### Пользовательский flow

- [x] несколько полей;
- [x] геолокация и ручные координаты;
- [x] культура, дата сезона и ручная фаза;
- [x] отдельные настройки уведомлений;
- [x] отчёт из реального Telegram-сценария;
- [x] `/start`, `/help`, `/cancel`.

### Данные и расчёты

- [x] typed weather DTO и provider port;
- [x] раздельные reanalysis / operational past / forecast;
- [x] локальный календарный день в классификации данных;
- [x] ГДД с `Tbase`, покрытием и пропусками;
- [x] ГТК без прогнозных осадков;
- [x] P−ET₀ без подстановки нулей;
- [x] frost screening только по прогнозным строкам;
- [x] явные scientific limitations.

### Очистка репозитория

- [x] удалена синтетическая Random Forest training pipeline;
- [x] удалены недостижимые Docker/legacy entrypoints;
- [x] удалены неподключённые эвристические climate/soil/satellite modules;
- [x] core и RAG зависимости разделены;
- [x] добавлена capability matrix.

## Выполняемый этап

### P0/P1 — научная целостность и воспроизводимая проверка

- [x] исправить period partition для текущего локального дня;
- [x] исправить false-zero в P−ET₀;
- [x] согласовать frost DTO и Telegram formatter;
- [x] добавить read-only live provider smoke;
- [x] добавить единый `verify-production.sh`;
- [x] получить зелёный CI полного среза;
- [ ] выполнить clean-host smoke на отдельной Debian 12 VM;
- [ ] выполнить реальный Telegram smoke после deployment.

## Следующие этапы

### P0 — интеграционные тесты

- [ ] PostgreSQL migration/repository tests на реальном PostgreSQL;
- [ ] Redis FSM restart test;
- [ ] конкурентный scheduler test с двумя процессами;
- [ ] mocked full HTTP contract Open-Meteo;
- [ ] deploy/update/failed-start rollback test.

### P1 — provider resilience

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

- зелёный CI полного дерева;
- live Open-Meteo smoke;
- отсутствие legacy/fake runtime;
- явное отключение неподдерживаемых возможностей;
- clean-host systemd deployment;
- проверенный Telegram flow для двух полей;
- документированный rollback и восстановление БД.
