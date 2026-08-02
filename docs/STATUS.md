# Статус разработки

Дата актуализации: **2026-08-02**.

## Текущее состояние

Проект находится на уровне **низкоресурсного code-level полевого пилота**. Production запускается одним aiogram-entrypoint, хранит поля и пользовательское состояние в PostgreSQL/Redis, выполняет агрометеорологические расчёты, фоновый GFS Ensemble screening и безопасно обновляется из зелёной ветки `main`.

Полевой smoke выявил и устранил пользовательские дефекты:

- Telegram больше не должен терять весь отчёт из-за символов `<`, `>` или `&` в обычном тексте;
- дата посева выбирается inline-календарём, ручной ввод оставлен резервом;
- на одной координатной точке можно хранить несколько культур;
- дата и фактическая фаза сохраняются отдельно для каждой культуры;
- погодные сигналы объединяются по периодам и объясняются физическими величинами без выдачи доли ансамбля за вероятность ущерба;
- дальний сигнал используется для планирования, а не называется устойчивым прогнозом;
- CAPE не выдаётся за прогноз грозы или града.

Проект не является самостоятельным источником критических решений: локальная станция, официальные предупреждения, осмотр поля и региональная валидация остаются обязательными.

## Production-контур MVP

```text
aiogram 3.x + SafeHtmlBot
PostgreSQL + SQLAlchemy 2 async + Alembic
Redis FSM / callback idempotency / renewable leases / deduplication
Open-Meteo Forecast Best Match + Historical Weather
Open-Meteo GFS Ensemble members
APScheduler
systemd service + update timer + heartbeat + rollback
GitHub Actions green-main release gate
```

Опционально и выключено по умолчанию:

```text
ERA5 current season + 1991–2020 reference
RAG / LLM advisor
```

## Подтверждённые пользовательские возможности

### Поля и культуры

- [x] несколько полей в одном Telegram-профиле;
- [x] геолокация и ручные координаты;
- [x] несколько культур на одной координатной точке;
- [x] выбор культуры для текущего отчёта и редактирования;
- [x] отдельные дата посева и фактическая фаза каждой культуры;
- [x] inline-календарь с переходом по месяцам и годам;
- [x] запрет будущих дат и поддержка прошлого года для озимых;
- [x] ручной ввод даты и `/cancel` как резервный сценарий;
- [x] команды `/crops` и `/report`.

### Отчёт и Telegram UX

- [x] один entrypoint `python -m src.bot.main`;
- [x] ручной агроотчёт выбранной культуры;
- [x] глобальное экранирование Telegram HTML;
- [x] повтор отправки без разметки при ошибке entities;
- [x] ошибка Telegram-разметки не подменяется сообщением об ошибке расчёта;
- [x] Redis FSM переживает рестарт;
- [x] replay-safe callbacks;
- [x] optional RAG Router не загружается при `RAG_ENABLED=false`.

### Данные и расчёты

- [x] раздельные `reanalysis / operational_past / forecast`;
- [x] GDD от локальной даты сезона с crop-specific `Tbase`;
- [x] сезонный ГТК только при непрерывном завершённом ряде;
- [x] provider ET₀ и `P−ET₀` без фиктивных нулей;
- [x] накопленные осадки/ET₀, сухие серии и Rx1day/Rx5day;
- [x] optional ERA5 current/reference одной моделью;
- [x] climate section fail-soft;
- [x] `CLIMATE_REFERENCE_ENABLED=false` предотвращает тяжёлые ERA5-запросы в production MVP.

### Ансамблевые погодные сигналы

- [x] GFS Ensemble Seamless до 16 суток;
- [x] Tmin, Tmax, суточные осадки, порывы и CAPE;
- [x] минимум 20 валидных вариантов по всем диагностическим переменным;
- [x] неполные сутки исключаются fail-closed;
- [x] соседние дни одного явления объединяются в период;
- [x] показываются физическое условие, число вариантов и основной разброс;
- [x] число вариантов не называется вероятностью события или повреждения;
- [x] приоритет действия учитывает заблаговременность;
- [x] все культуры точки перечисляются, но повреждение каждой отдельно не заявляется;
- [x] CAPE называется признаком неустойчивой атмосферы, а не прогнозом града;
- [x] ручной обзор `/risks`, история `/history`, compact digest и quiet hours.

### Сохранённые поля и scheduler

- [x] source of truth — PostgreSQL `fields / crop_seasons`;
- [x] scheduler выбирает все alert-enabled fields, а не только активное;
- [x] погодный запрос выполняется на координатную точку, а не отдельно на каждую культуру;
- [x] первый risk cycle запускается после здорового старта;
- [x] дальнейший screening выполняется каждые 6 часов;
- [x] поля обрабатываются последовательно для слабого сервера;
- [x] Redis lease исключает параллельный цикл двух workers;
- [x] accepted run сохраняется до Telegram side effect;
- [x] state/daily deduplication защищает от повторной доставки.

## Запуск, обновление и ресурсы

- [x] PostgreSQL, Redis и Alembic head проверяются до запуска;
- [x] реальный Telegram `getMe` выполняется до `READY=1`;
- [x] heartbeat начинается после успешной Telegram-проверки;
- [x] CI выполняет production startup-smoke без Telegram-сети;
- [x] update timer проверяет `main` каждые 15 минут;
- [x] устанавливается только точный SHA с зелёным required CI;
- [x] pending/failed/API error оставляет текущий release активным;
- [x] atomic activation и verified rollback;
- [x] content-addressed shared virtualenv;
- [x] `BLOCKING_IO_WORKERS=2`, BLAS/OpenMP=1;
- [x] systemd `MemoryHigh=384M`, `TasksMax=64`, без жёсткого `MemoryMax`;
- [x] RAG и многолетнее ERA5-сравнение выключены в базовом профиле.

## Автоматические gates

GitHub CI проверяет:

- Python 3.10 и основной Python runtime;
- Ruff и `compileall`;
- Bash syntax и ShellCheck;
- repository legacy/scientific-claims policies;
- production MVP startup-smoke;
- календарь, multi-crop profiles, Telegram HTML и farmer-facing risk language;
- unit/contract tests;
- PostgreSQL/Redis integration;
- backup/restore round trip;
- Alembic graph;
- применимые live provider contracts.

## Научные ограничения

- GFS и ERA5 — модельные сетки, не локальная станция.
- Число членов ансамбля требует архивной калибровки, прежде чем называться вероятностью.
- Доля членов одного запуска не доказывает временную устойчивость сигнала.
- Tmin/Tmax воздуха 2 м не являются температурой растения или damage model.
- Crop-specific `Tbase/Tupper` требуют versioned cultivar/region validation.
- Provider ET₀ не является фактической ET культуры или дозой полива.
- CAPE без подъёма, влаги, CIN, сдвига ветра и уровня замерзания не является прогнозом грозы или града.
- Валидированный прогноз болезней, града, ущерба и урожайности отсутствует.
- SPI/SPEI по короткому прогнозу не вычисляются.

## Незакрытые внешние gates

- [ ] подтвердить автоматическое получение нового `main` на целевом сервере;
- [ ] повторить real Telegram smoke для календаря, нескольких культур, отчёта и фонового digest;
- [ ] clean Debian 12 deploy/reboot/update/rollback evidence;
- [ ] forced release failure и rollback на реальном systemd host;
- [ ] Astra Linux smoke;
- [ ] station comparison для GFS/ERA5/ET₀/ГТК;
- [ ] screening-only регламент и независимый официальный warning channel.

## Следующие приоритеты

### P0

1. real Telegram acceptance обновлённого пользовательского сценария;
2. evidence green-main auto-update/rollback на целевом сервере;
3. station comparison protocol;
4. полевой журнал наблюдений и операций.

### P1

1. provider latency/error/cache/fallback metrics;
2. простой circuit breaker и stale-cache age;
3. окно полевых работ;
4. official CAP warning layer;
5. station ingestion и forecast matching;
6. below-threshold evaluations;
7. переименование `frost_alerts_enabled`;
8. удаление перехваченных legacy crop/season/report handlers после отдельного рефакторинга;
9. постепенные mypy/Bandit gates.

Подробности UX: `docs/FARMER_UX.md`.  
Эксплуатация: `docs/LOW_RESOURCE_MVP.md`.  
Глубокий аудит: `docs/DEEP_AUDIT_2026-07-19.md`.

## Готовность

**Code-level:** основной Telegram-flow, календарь, несколько культур, безопасный отчёт, понятные погодные сигналы, scheduler и green-main CD реализованы и должны проходить автоматические gates.

**Полевой продукт:** требует повторной приёмки на реальном Telegram и региональной station validation.
