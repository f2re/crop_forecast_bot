# Статус разработки

Дата актуализации: **2026-07-27**.

## Текущее состояние

Проект переведён в профиль **низкоресурсного code-level полевого пилота**. Основной Telegram-flow, сохранённые поля, агрометеорологические расчёты, ансамблевые риски, история, настройки доставки и native systemd release остаются рабочими.

Новый MVP-контур добавляет:

- проверку реального Telegram token до systemd readiness;
- офлайн production startup-smoke в GitHub CI;
- один отложенный расчёт всех сохранённых alert-enabled fields после запуска;
- автоматическую проверку `main` каждые 15 минут;
- развёртывание только точного SHA с зелёным GitHub Actions CI;
- shallow clone только после обнаружения нового green commit;
- повторное использование content-addressed virtualenv;
- ограниченный executor и один BLAS/OpenMP thread;
- мягкие systemd resource controls;
- production MVP без RAG и многолетних ERA5-запросов по умолчанию.

Проект всё ещё не принят как самостоятельный источник критических полевых решений: внешняя установка, реальный Telegram-flow и станционная проверка остаются обязательными gates.

## Production-контур MVP

```text
aiogram 3.x
PostgreSQL + SQLAlchemy 2 async + Alembic
Redis FSM / callback idempotency / renewable leases / deduplication
Open-Meteo Forecast Best Match + Historical Weather
Open-Meteo GFS Ensemble members
APScheduler
systemd service + update timer + heartbeat + rollback
GitHub Actions green-main release gate
```

Опционально:

```text
ERA5 current season + 1991–2020 reference
RAG / LLM advisor
```

Обе опции отключены в production MVP по умолчанию.

## Подтверждённые возможности

### Telegram

- [x] один entrypoint `python -m src.bot.main`;
- [x] несколько полей;
- [x] геолокация и ручные координаты;
- [x] культура, дата сезона и наблюдаемая фаза;
- [x] ручной агроотчёт;
- [x] ручной 16-суточный обзор рисков через `/risks`;
- [x] история и тренд через `/history`;
- [x] настройки уведомлений по полю;
- [x] режимы `immediate / digest / high_only`;
- [x] тихие часы `off / 22:00–07:00 / 23:00–06:00`;
- [x] высокий риск обходит тихие часы и обычный digest;
- [x] Redis FSM restart и replay-safe callbacks;
- [x] optional RAG router не загружается при `RAG_ENABLED=false`.

### Данные и расчёты

- [x] раздельные `reanalysis / operational_past / forecast`;
- [x] GDD от локальной даты сезона с crop-specific `Tbase`;
- [x] сезонный ГТК только при непрерывном завершённом ряду;
- [x] provider ET₀ и `P−ET₀` без фиктивных нулей;
- [x] накопленные осадки/ET₀, сухие серии и Rx1day/Rx5day;
- [x] ERA5 current/reference одной моделью, база 1991–2020;
- [x] общий полный current climate prefix для `Tmean/P/ET₀`;
- [x] empirical percentiles без выдачи за probability/SPI/SPEI;
- [x] climate section fail-soft;
- [x] `CLIMATE_REFERENCE_ENABLED=false` предотвращает большие ERA5-запросы в production MVP.

### Расчёты сохранённых полей

- [x] source of truth — PostgreSQL `fields` и active `crop_seasons`;
- [x] scheduler выбирает все поля с включённым типом уведомления, а не только активное поле;
- [x] первый weather-risk cycle запускается после здорового старта с задержкой 120 секунд;
- [x] дальнейший GFS Ensemble screening выполняется каждые 6 часов;
- [x] все поля обрабатываются последовательно, без всплеска параллельных запросов;
- [x] Redis lease исключает параллельный cycle двух workers;
- [x] accepted run сохраняется до Telegram side effect;
- [x] state/daily deduplication защищает от повторного сообщения после рестарта.

### Ансамблевые риски

- [x] GFS Ensemble Seamless, до 16 суток;
- [x] Tmin, Tmax, осадки, порывы и CAPE;
- [x] холод, жара, сильные осадки, ветер и конвективная неустойчивость;
- [x] минимум 20 валидных членов по всем диагностическим переменным;
- [x] fail-closed exclusion неполных суток;
- [x] `k/n`, P10, медиана, P90 и заблаговременность;
- [x] `k/n` не называется откалиброванной вероятностью;
- [x] CAPE не называется прогнозом грозы или града;
- [x] один compact digest на поле вместо серии сообщений;
- [x] persistent risk history и delivery states.

### Запуск и healthcheck

- [x] runtime environment валидируется до запуска;
- [x] PostgreSQL ping и Alembic head обязательны;
- [x] Redis ping входит в preflight;
- [x] writable paths проверяются;
- [x] реальный Telegram `getMe` выполняется до `READY=1`;
- [x] heartbeat начинается только после успешной Telegram-проверки;
- [x] CI запускает `python -m src.bot.main --startup-smoke` без Telegram-сети;
- [x] startup-smoke собирает production Router graph, DB, Redis, coordination и scheduler.

### Автоматическое обновление

- [x] update timer включается по умолчанию;
- [x] интервал проверки `main` — 15 минут плюс небольшой random delay;
- [x] `git ls-remote` выполняется до clone/build;
- [x] тот же SHA завершает update без создания release;
- [x] обязательный `ci.yml` push-run проверяется для точного SHA;
- [x] optional provider smoke, если зарегистрирован для SHA, также должен быть зелёным;
- [x] pending/failed/API error оставляет текущий release активным;
- [x] branch race обнаруживается повторной проверкой cloned SHA;
- [x] PostgreSQL backup, Alembic, preflight, activation и rollback сохранены;
- [x] virtualenv повторно используется до изменения Python minor/requirements.

### Ресурсный профиль

- [x] базовый installer не ставит GDAL, compiler toolchain и RAG dependencies;
- [x] `BLOCKING_IO_WORKERS=2`;
- [x] BLAS/OpenMP threads ограничены одним;
- [x] systemd `MemoryHigh=384M`, `TasksMax=64`, пониженные CPU/IO weights;
- [x] жёсткий `MemoryMax` отсутствует;
- [x] default retention risk history — 30 суток;
- [x] default retention — два release и три backup;
- [x] PostgreSQL и Redis сохранены как обязательный надёжный минимум.

## Автоматические gates

GitHub CI проверяет:

- Ruff и `compileall`;
- Bash syntax и ShellCheck;
- repository legacy/scientific-claims policies;
- production MVP startup-smoke;
- unit/contract tests;
- PostgreSQL/Redis integration;
- pytest log artifacts;
- backup/restore round trip;
- Alembic graph;
- live operational Open-Meteo contract;
- live homogeneous ERA5 contract;
- live GFS Ensemble contract.

## Научные ограничения

- GFS и ERA5 — модельные сетки, не локальная станция.
- `k/n` требует архивной калибровки, прежде чем называться вероятностью.
- Risk history сохраняет threshold-crossing events; для unbiased reliability нужны below-threshold evaluations и observations.
- Tmin воздуха 2 м не является температурой растения или damage model.
- Crop-specific `Tbase/Tupper` требуют versioned cultivar/region validation.
- Provider ET₀ не является фактической ET культуры или дозой полива.
- Валидированный прогноз града, болезней и урожайности отсутствует.
- SPI/SPEI по короткому прогнозу не вычисляются.

## Незакрытые внешние gates

- [ ] clean Debian 12 deploy, migration, reboot и timer evidence;
- [ ] реальный Telegram smoke для нескольких пользователей и полей;
- [ ] forced release failure и rollback на реальном systemd host;
- [ ] проверка автообновления после реального merge в `main` на целевом сервере;
- [ ] Astra Linux smoke;
- [ ] station comparison для GFS/ERA5/ET₀/ГТК;
- [ ] screening-only регламент и независимый официальный канал.

## Следующие приоритеты

### P0

1. clean-host и real Telegram acceptance;
2. evidence автоматического green-main update/rollback на целевом сервере;
3. station comparison protocol;
4. operator runbook;
5. полевой журнал наблюдений и операций.

### P1

1. provider latency/error/cache/fallback metrics;
2. простой circuit breaker и stale-cache age;
3. окно полевых работ;
4. official CAP warning layer;
5. station ingestion и forecast matching;
6. below-threshold evaluations;
7. переименование `frost_alerts_enabled`;
8. разделение `scheduler.py` и `handlers/core.py`;
9. постепенные mypy/Bandit gates.

Подробности эксплуатации: `docs/LOW_RESOURCE_MVP.md`.  
Глубокий аудит: `docs/DEEP_AUDIT_2026-07-19.md`.

## Готовность

**Code-level:** MVP startup, saved-field scheduling, green-main pull-based CD, rollback и low-resource controls покрыты автоматическими контрактами.

**Полевой продукт:** не принят до clean-host, real Telegram и региональной station validation.
