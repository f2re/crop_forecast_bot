# План модернизации Crop Forecast Bot

## Целевая архитектура

```text
Telegram
  -> aiogram handlers / persistent FSM
      -> application services / ports
          -> domain/agro calculations
              -> infrastructure adapters
                  -> Open-Meteo forecast / historical reanalysis
                  -> PostgreSQL repositories / Alembic
                  -> Redis FSM / locks / deduplication
                  -> RAG adapters
```

Правила:

- один Telegram framework: aiogram 3.x;
- один production entrypoint: `python -m src.bot.main`;
- handlers не выполняют расчёты, прямые HTTP-вызовы и блокирующие операции;
- все I/O-контракты асинхронные и типизированные;
- PostgreSQL — source of truth, Redis — FSM/cache/locks;
- наблюдения, реанализ, оперативное прошлое модели и прогноз разделяются;
- fallback виден пользователю и не повышает заявленную точность;
- формулы имеют источник, единицы, период применимости и тесты;
- production разворачивается нативно Bash-скриптами и управляется systemd;
- релиз принимается только после зелёного CI и clean-host smoke test.

## Этап 0 — стабилизация runtime

Статус: **выполнено**.

- [x] удалить telebot entrypoint и конфликтующий handlers module;
- [x] подключить основной aiogram Router/FSM;
- [x] перенести поле, координаты, культуру, отчёт и уведомления;
- [x] убрать глобальные user state dictionaries;
- [x] унифицировать Open-Meteo DTO и async API;
- [x] исправить DB session contract scheduler;
- [x] согласовать frost result и formatter;
- [x] добавить штатный startup/shutdown БД, bot session, storage и scheduler;
- [x] добавить Redis FSM policy, heartbeat и systemd watchdog;
- [x] добавить native deploy/update/rollback/status scripts;
- [x] добавить atomic releases и PostgreSQL backup перед update;
- [x] удалить альтернативные deployment-контуры;
- [x] добавить CI и unit tests.

Критерий готовности: основной Telegram-путь работает из единственного aiogram-entrypoint.

## Этап 1 — миграции и надёжность состояния

Приоритет: P0. Статус: **основной production-срез выполнен**.

- [x] создать Alembic baseline из фактической модели;
- [x] принять БД, ранее созданную через `create_all()`;
- [x] убрать `Base.metadata.create_all()` из production startup;
- [x] проверять Alembic head при запуске и в runtime doctor;
- [x] сделать `alembic upgrade head` обязательным в deploy/update;
- [x] перенести alert deduplication в Redis `SET NX EX` с token lease;
- [x] добавить distributed scheduler lock;
- [x] исключить повтор ежедневного отчёта одному полю в пределах даты;
- [x] освободить DB session до длительных HTTP/Telegram операций scheduler;
- [x] добавить модель `Field`:
  - имя и идентификатор;
  - координаты;
  - timezone;
  - высота модели;
  - active flag;
- [x] добавить модель `CropSeason`:
  - культура;
  - дата посева/начала сезона;
  - фактическая фаза;
  - источник и confidence фазы;
  - active flag;
- [x] перенести legacy-координаты и культуру в активное поле/сезон миграцией;
- [x] покрыть repository roundtrip и migration backfill тестами;
- [ ] поддержать несколько полей и безопасное переключение active field;
- [ ] обработать restart во время FSM сценарными тестами;
- [ ] добавить интеграционные тесты PostgreSQL/Redis в изолированной среде;
- [ ] проверить конкурентный запуск двух scheduler-процессов с реальным Redis.

Критерий готовности: рестарт процесса не теряет профиль поля и не дублирует уведомления.

## Этап 2 — provider layer

Приоритет: P0/P1. Статус: **Open-Meteo vertical slice выполнен, остальные провайдеры впереди**.

- [x] ввести application port и DTO для погодного провайдера;
- [x] разделить forecast и historical reanalysis в метаданных строк;
- [x] добавить coverage metadata: requested/actual period, completeness, notes;
- [x] ограничить синхронный vendor-client worker thread и semaphore;
- [x] добавить timeout, retry и файловый cache для Open-Meteo;
- [x] реализовать controlled fallback при недоступности сезонного реанализа;
- [x] покрыть parsing/merge/source precedence unit-тестами;
- [ ] выделить общий HTTP client lifecycle вместо отдельных sync sessions;
- [ ] добавить jitter, rate limiter и circuit breaker;
- [ ] добавить mocked HTTP integration tests полного Open-Meteo adapter;
- [ ] определить DTO для observation, soil и satellite providers;
- [ ] SoilGrids validation, включая ocean/no-data;
- [ ] ERA5-Land job state, CDS queue и cache integrity;
- [ ] выбрать Sentinel/MODIS provider после проверки реального доступа и квот;
- [ ] удалить либо изолировать Google Earth Engine dependency, если credentials не поддерживаются.

Критерий готовности: outage провайдера даёт контролируемый degraded output, а не выдуманную рекомендацию.

## Этап 3 — научный расчётный слой

Приоритет: P0.

### ГДД

- [x] дата посева/начала сезона настраивается пользователем;
- [x] `Tbase` берётся из единого crop catalogue;
- [x] реанализ, operational past и forecast разделяются;
- [x] сезонная сумма заявляется только при покрытии даты начала;
- [x] выводятся valid/expected/missing days и missing fraction;
- [x] автоматическая фенофаза отключена до научной валидации;
- [ ] добавить crop-specific optional upper cutoff;
- [ ] валидировать пороги фаз по культуре и региону;
- [ ] тесты leap year, DST, season boundary и длинных пропусков.

### ГТК

- [x] считать только по суткам с `Tmean > 10°C`;
- [x] требовать минимальное число валидных тёплых суток;
- [x] не называть 14-дневное окно сезонным;
- [ ] использовать согласованный сезонный observation/reanalysis ряд;
- [ ] вывести missing-data fraction именно для окна ГТК;
- [ ] определить правила непрерывности вегетационного периода.

### ET₀ и водный баланс

- [x] обозначать ET₀ как provider variable;
- [ ] локальная FAO-56 Penman–Monteith со всеми входными параметрами;
- [ ] Kc и root-zone model только с явной фазой и почвенным контекстом;
- [ ] не выдавать дозу полива без проверяемого контекста.

### Заморозки

- [x] учитывать local time модели и высоту как контекст;
- [x] передавать культуру и фактическую фазу в отчёт/алерт;
- [x] явно разделять Tmin воздуха 2 м и температуру поверхности;
- [x] не выдавать общие 2/0°C за crop-specific damage threshold;
- [ ] валидировать пороги чувствительности по культуре и фазе;
- [ ] terrain correction и cold-air drainage;
- [ ] ensemble/probabilistic uncertainty;
- [ ] validation metrics: POD, FAR, CSI, lead time.

### SPI

- [ ] длинный однородный месячный ряд осадков;
- [ ] distribution fitting и goodness-of-fit;
- [x] не вычислять SPI по короткому прогнозу.

Критерий готовности: каждый показатель имеет источник, единицы, валидный период, uncertainty note и тесты.

## Этап 4 — Telegram UX

Приоритет: P1. Статус: **основной сценарий с сезоном доступен**.

- [x] основной flow: field → crop → season → report;
- [x] `/start`, `/help`, `/cancel` и Telegram command menu;
- [x] ввод даты в ISO и русском формате;
- [x] ручной выбор фактически наблюдаемой фазы;
- [x] очистка ручной фазы;
- [x] progress без обещания неподтверждённого времени;
- [x] отчёт содержит what/reliability/action/recheck sections;
- [x] fallback сезонного ряда явно показан пользователю;
- [ ] back/cancel на каждом callback и FSM branch;
- [ ] duplicate callback protection и idempotency keys;
- [ ] редактирование имени поля и timezone пользователем;
- [ ] notification windows и quiet hours;
- [ ] administrator diagnostics: provider status, queue, alerts, error export;
- [ ] сценарные тесты через aiogram mocks/test utilities;
- [ ] restart test посреди ввода даты сезона.

Критерий готовности: полный сценарий достижим из `/start` и переживает restart.

## Этап 5 — RAG и рекомендации

Приоритет: P1/P2.

- [x] передавать в RAG активное поле, сезонную дату и фактическую фазу;
- [x] не подменять недоступные погодные данные выдуманным контекстом;
- [ ] lazy RAG initialization;
- [ ] optional dependency profile для embeddings;
- [ ] metadata документа: версия, страница, категория, дата;
- [ ] citation validation;
- [ ] запрет доз/препаратов без нормативного источника и контекста;
- [ ] prompt-injection resistance и source-only mode;
- [ ] evaluation set русскоязычных агрономических вопросов;
- [ ] удалить заявления о model accuracy до независимой валидации.

Критерий готовности: существенная рекомендация опирается на источник либо прозрачный детерминированный расчёт.

## Этап 6 — operations и release engineering

Приоритет: P1.

- [ ] сгенерировать и проверить `uv.lock` на целевых платформах;
- [ ] dependency profiles: core, climate, satellite, rag, dev;
- [x] Alembic migration обязательна в deploy/update;
- [x] concise operator README и `scripts/help.sh`;
- [ ] clean-host smoke test `deploy.sh` на Debian 12;
- [ ] automated atomic update и failed-start rollback test;
- [ ] backup/restore runbook с периодической проверкой restore;
- [ ] тест systemd watchdog через намеренную блокировку event loop;
- [ ] JSON logging, correlation ID и error metrics;
- [ ] Prometheus/OpenTelemetry либо минимальный local metrics endpoint;
- [ ] release tags и changelog;
- [ ] signed/verified release source policy;
- [ ] тест Astra Linux 1.7;
- [ ] support policy для внешних PostgreSQL/Redis.

Критерий готовности: clean host устанавливается, обновляется, диагностируется и откатывается документированными Bash-командами.

## Definition of Done ближайшего релиза

- один aiogram entrypoint;
- полный field/crop/season/report сценарий в Telegram;
- PostgreSQL, Redis и scheduler contracts покрыты integration tests;
- outage Open-Meteo имеет явное degraded behavior;
- ГТК/ГДД/ET₀/frost period-correct и научно маркированы;
- Alembic обязателен на startup/update;
- native deploy/update/rollback и watchdog проходят clean-host tests;
- CI без ошибок tests/types/shell/security;
- отсутствуют telebot, глобальное состояние и неподтверждённые заявления о точности.
