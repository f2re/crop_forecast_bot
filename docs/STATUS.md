# Статус разработки

Дата актуализации: **2026-07-13**.

Текущий вертикальный срез: **PR #29 — release rollback, backup restore verification и live provider gates**. Полный CI прошёл, включая реальные PostgreSQL/Redis integration tests и `pg_dump → pg_restore` с непустыми данными.

## Production-контур

```text
aiogram 3.x
PostgreSQL + Alembic
Redis FSM / callback idempotency / renewable leases / deduplication
Open-Meteo Forecast + bounded Historical Weather
ERA5-Land current season + 1991–2020 reference via Open-Meteo
APScheduler
systemd + versioned Bash releases
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

### Оперативные, накопленные и климатические показатели

- [x] typed weather и climate ports/DTO;
- [x] раздельные `reanalysis / operational_past / forecast`;
- [x] текущий локальный день не считается завершённым прошлым;
- [x] ГДД строго от локальной даты начала сезона;
- [x] ГТК без прогнозных осадков;
- [x] P−ET₀ без подстановки нулей;
- [x] накопленные `P`, provider `ET₀` и парная `ΣP−ΣET₀`;
- [x] ETCCDI dry/wet threshold `1 мм/сут`;
- [x] текущая и максимальная сухая серия на непрерывном ряду;
- [x] максимумы осадков за 1 и 5 последовательных суток;
- [x] homogeneous ERA5-Land current/reference с одной моделью `era5_land`;
- [x] фиксированная база 1991–2020 и same-length windows;
- [x] минимум 20 валидных reference-лет;
- [x] empirical percentiles без distribution fit;
- [x] температура сравнивается аддитивно, без `% от среднего`;
- [x] outage climate provider не блокирует основной отчёт;
- [x] результат не называется station normal, probability, SPI или SPEI.

### Release engineering — PR #29

- [x] systemd-unit устанавливаются из точного release, который активируется;
- [x] deploy/update/manual rollback используют одну реализацию unit rendering;
- [x] failed activation восстанавливает предыдущие код и unit-файлы вместе;
- [x] восстановленный release обязан пройти `active + heartbeat`;
- [x] failed initial activation без предыдущего release удаляет broken `current` и останавливает service;
- [x] state/cache/log paths централизованно рендерятся в systemd-unit;
- [x] release state machine покрыт детерминированными Bash/Python tests;
- [x] backup восстанавливается в изолированную PostgreSQL database;
- [x] сравниваются schema fingerprint, Alembic revision и точные fingerprints `users/fields/crop_seasons`;
- [x] CI выполняет restore round trip с непустым user/field/season fixture;
- [x] `verify-production.sh` поддерживает `--live-provider`, `--live-climate`, `--live-all`;
- [x] live ERA5-Land smoke проверяет homogeneous provenance, coverage, reference years и обязательные metrics;
- [x] добавлен weekly/manual GitHub Actions workflow с JSON artifacts;
- [x] полный CI PR #29: Ruff, compileall, ShellCheck, policy, unit/contract, PostgreSQL/Redis integration, backup restore, Alembic graph.

## Что ещё требует внешней среды

Следующие проверки нельзя достоверно заменить обычным GitHub-hosted CI:

- [ ] чистая Debian 12 VM: установка из документированной команды;
- [ ] reboot и автоматический systemd startup;
- [ ] реальный Telegram API smoke для двух полей с production token;
- [ ] intentionally failed release на реальном systemd host;
- [ ] первый успешный weekly/manual live provider workflow с сохранённым artifact;
- [ ] smoke на поддерживаемом Astra Linux окружении;
- [ ] сравнение ERA5-Land и provider ET₀ с локальной станцией/лизиметром.

> Telegram Bot API не предоставляет application idempotency key для `sendMessage`. Абсолютный exactly-once результат между внешней отправкой и Redis dedup недоказуем; бот не должен быть единственным каналом критических предупреждений.

## Следующие этапы

### P0 — внешняя приёмка

- [ ] clean-host Debian deploy/reboot/update/forced-failure/rollback;
- [ ] Telegram two-field smoke до и после rollback;
- [ ] Astra Linux smoke;
- [ ] operator runbook для неоднозначного Telegram send result.

### P1 — provider resilience и наблюдаемость

- [ ] jittered retry и circuit breaker;
- [ ] измеримый rate limiter;
- [ ] stale-cache fallback с возрастом данных;
- [ ] provider latency/error/fallback metrics;
- [ ] отдельная телеметрия больших climate-запросов;
- [ ] прямой CDS/ERA5-Land queued job/object-cache pipeline.

### P1 — научная валидация

- [ ] versioned sources для `Tbase/Tupper`;
- [ ] crop/region/cultivar validation;
- [ ] frost thresholds по культуре и фазе;
- [ ] surface temperature, terrain и ensemble inputs;
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
- [x] homogeneous ERA5-Land comparison с QC и Telegram tests;
- [x] version-consistent release/unit rollback state machine;
- [x] реальный PostgreSQL backup/restore round trip в CI;
- [ ] clean-host deployment и reboot;
- [ ] реальный Telegram smoke;
- [ ] live provider evidence artifact;
- [ ] параллельная проверка с локальной станцией;
- [ ] эксплуатационные метрики и утверждённый screening-only регламент.
