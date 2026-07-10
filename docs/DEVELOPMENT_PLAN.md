# План модернизации Crop Forecast Bot

## Целевая архитектура

```text
Telegram
  → aiogram handlers / persistent FSM
    → application services / ports
      → domain and agro calculations
        → infrastructure adapters
          ├─ Open-Meteo forecast / historical reanalysis
          ├─ PostgreSQL repositories / Alembic
          ├─ Redis FSM / locks / deduplication
          └─ RAG adapters
```

Правила проекта:

- один Telegram framework и entrypoint;
- handlers не выполняют расчёты, HTTP и блокирующие операции;
- все I/O-контракты async и типизированы;
- PostgreSQL — source of truth;
- Redis — persistent FSM, locks и deduplication;
- observations, reanalysis, operational past и forecast разделяются;
- fallback всегда виден пользователю;
- формулы имеют источник, единицы, период применимости и тесты;
- production устанавливается Bash-скриптами и управляется systemd;
- merge разрешён только после зелёного CI.

## Этап 0 — стабилизация runtime

Статус: **выполнено**.

- [x] единый aiogram 3.x entrypoint;
- [x] удаление telebot и глобальных user state dictionaries;
- [x] основной Router/FSM;
- [x] единый async Open-Meteo contract;
- [x] корректный DB/scheduler lifecycle;
- [x] heartbeat, readiness и systemd watchdog;
- [x] native deploy/update/rollback/status;
- [x] CI, unit tests и запрет контейнерных deployment-файлов.

## Этап 1 — схема, состояние и multi-field profile

Приоритет: P0. Статус: **production vertical slice выполнен**.

- [x] Alembic baseline и принятие legacy `create_all()` schema;
- [x] обязательный `alembic upgrade head` в deploy/update;
- [x] проверка schema revision при startup;
- [x] Redis notification deduplication и distributed scheduler lock;
- [x] `Field`: имя, координаты, timezone, высота, metadata source, active flag;
- [x] `CropSeason`: культура, дата посева/начала, фактическая фаза и source;
- [x] миграция legacy coordinates/crop в `Основное поле`;
- [x] несколько полей в Telegram;
- [x] создание, переименование, обновление координат и переключение active field;
- [x] ownership checks и case-insensitive duplicate validation;
- [x] отдельные daily/frost settings каждого поля;
- [x] тесты независимости сезона и уведомлений двух полей;
- [ ] restart FSM scenario tests;
- [ ] real PostgreSQL/Redis integration tests;
- [ ] concurrent two-process scheduler test;
- [ ] cleanup migration legacy columns после production verification.

Критерий: переключение активного поля атомарно восстанавливает его crop/season/phase/settings, а restart не теряет FSM progress.

## Этап 2 — provider layer

Приоритет: P0/P1. Статус: **Open-Meteo slice выполнен**.

- [x] WeatherProvider port и domain DTO;
- [x] forecast/reanalysis source classification;
- [x] coverage metadata и controlled degraded mode;
- [x] bounded worker, retry и cache;
- [x] unit tests history parsing/merge precedence;
- [ ] общий async HTTP lifecycle;
- [ ] retry jitter, rate limiter и circuit breaker;
- [ ] mocked full Open-Meteo integration tests;
- [ ] observation provider DTO;
- [ ] ERA5-Land/CDS job lifecycle и cache integrity;
- [ ] SoilGrids adapter с ocean/no-data validation;
- [ ] Sentinel-2/MODIS provider после проверки доступа и квот;
- [ ] изоляция optional Google Earth Engine dependency.

Критерий: outage любого provider приводит к контролируемому degraded report без выдуманных данных.

## Этап 3 — научный расчётный слой

Приоритет: P0.

### ГДД

- [x] настраиваемая дата сезона;
- [x] crop-specific `Tbase` из единого catalogue;
- [x] разделение reanalysis/operational/forecast;
- [x] coverage и missing fraction;
- [x] запрет автоматической фазы до валидации;
- [ ] optional upper temperature cutoff;
- [ ] независимая валидация phase thresholds по культурам/регионам;
- [ ] leap year, DST, season boundary и long-gap tests.

### ГТК

- [x] только сутки `Tmean > 10°C`;
- [x] minimum valid warm days;
- [x] короткое окно не называется сезонным;
- [ ] согласованный сезонный observation/reanalysis ряд;
- [ ] missing fraction для окна ГТК;
- [ ] правила непрерывности вегетационного периода.

### ET₀ и водный баланс

- [x] provider ET₀ явно маркирован;
- [ ] локальная FAO-56 Penman–Monteith;
- [ ] Kc/root-zone model только с phase/soil context;
- [ ] запрет доз полива без проверяемого контекста.

### Заморозки

- [x] local time, crop, manual phase и elevation как контекст;
- [x] air 2 m отделён от plant/surface temperature;
- [x] общие 2/0°C не названы damage thresholds;
- [ ] crop/phase susceptibility sources;
- [ ] surface temperature provider/estimate;
- [ ] terrain correction и cold-air drainage;
- [ ] ensemble uncertainty;
- [ ] POD/FAR/CSI/lead-time validation.

### SPI

- [x] не рассчитывать по короткому прогнозу;
- [ ] длинный однородный месячный ряд;
- [ ] distribution fitting и goodness-of-fit.

Критерий: каждый показатель имеет источник, единицы, валидный период, uncertainty note и тесты.

## Этап 4 — Telegram UX

Приоритет: P1. Статус: **основной multi-field flow доступен**.

- [x] fields → active field → crop → season → report;
- [x] `/start`, `/help`, `/cancel`;
- [x] список, создание, rename и coordinate update;
- [x] ручная дата и фактическая фаза;
- [x] field-level notification settings;
- [x] compact report: what/reliability/action/recheck;
- [x] explicit progress и fallback;
- [ ] delete/archive field flow с подтверждением;
- [ ] back/cancel на каждом callback branch;
- [ ] duplicate callback/idempotency middleware;
- [ ] user-editable timezone;
- [ ] notification hour/quiet hours per field;
- [ ] admin diagnostics and error export;
- [ ] aiogram scenario tests;
- [ ] restart test в середине create-field/date FSM.

Критерий: полный сценарий достижим из `/start`, идемпотентен и переживает restart.

## Этап 5 — RAG и рекомендации

Приоритет: P1/P2.

- [x] field/season/phase context в RAG;
- [x] отсутствие выдуманного weather context при fallback;
- [ ] lazy initialization;
- [ ] optional dependency profile;
- [ ] document metadata: version/page/category/date;
- [ ] citation validation;
- [ ] source-only mode и prompt-injection resistance;
- [ ] запрет доз/препаратов без нормативного источника;
- [ ] Russian agronomy evaluation set;
- [ ] удалить accuracy claims до независимой валидации.

## Этап 6 — operations и release engineering

Приоритет: P1.

- [x] native systemd deployment;
- [x] atomic releases, backup и rollback;
- [x] mandatory Alembic migration;
- [x] operator README, QUICK_START и `scripts/help.sh`;
- [ ] clean-host Debian 12 smoke test;
- [ ] Astra Linux smoke test;
- [ ] automated failed-start rollback test;
- [ ] periodic PostgreSQL restore verification;
- [ ] systemd watchdog fault-injection test;
- [ ] `uv.lock` на целевых платформах;
- [ ] dependency profiles: core/climate/satellite/rag/dev;
- [ ] JSON logging, correlation ID и metrics;
- [ ] release tags, changelog и source verification policy.

## Ближайший следующий вертикальный срез

1. Реальные PostgreSQL/Redis integration tests.
2. FSM restart tests для создания поля и ввода даты.
3. Field archive/delete с подтверждением и безопасным выбором нового active field.
4. Notification local hour и quiet hours.
5. Mocked Open-Meteo end-to-end contract tests.

## Definition of Done ближайшего релиза

- один aiogram entrypoint;
- несколько полей с независимыми season/settings;
- актуальная Alembic schema;
- Redis locks/deduplication;
- controlled Open-Meteo fallback;
- научно корректные подписи ГДД/ГТК/ET₀/frost;
- native deploy/update/rollback;
- зелёные Python, shell и unit/integration checks;
- отсутствие telebot, Docker runtime, global user state и unsupported accuracy claims.

## Сквозной scientific/data-quality срез 2026-07-10

- [x] source-label partition для reanalysis/operational past/forecast;
- [x] запрет фиктивного нуля ET₀-баланса при пропусках;
- [x] прогноз исключён из ГТК;
- [x] frost screening использует только forecast rows;
- [x] capability matrix и запрет synthetic ML runtime;
- [ ] реальные PostgreSQL/Redis/API integration tests на clean host.
