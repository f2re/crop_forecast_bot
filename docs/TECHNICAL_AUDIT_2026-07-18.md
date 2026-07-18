# Технический аудит Crop Forecast Bot

Дата: **2026-07-18**  
Проверяемая ветка: `main` после PR #41.

## Резюме

Проект находится в состоянии **code-level полевого пилота**. Основной Telegram-сценарий, хранение полей и сезонов, оперативный агроотчёт, ансамблевые предупреждения, ручной обзор рисков и журнал изменения сигнала реализованы и покрыты CI.

Статус **«готов к самостоятельной эксплуатации в поле» не подтверждён**, поскольку отсутствуют clean-host/reboot/rollback evidence, реальный Telegram smoke с production token и региональная проверка по локальным станциям.

Главный технический вывод: дальнейшее развитие не требует новой платформы или универсального фреймворка. Нужны небольшие вертикальные срезы, сокращение двух крупных модулей, эксплуатационная наблюдаемость и внешняя валидация.

## Что проверено

- единый aiogram 3.x entrypoint `python -m src.bot.main`;
- PostgreSQL + SQLAlchemy 2 async + Alembic;
- Redis FSM, callback idempotency, renewable leases и notification deduplication;
- graceful startup/shutdown для bot, DB, Redis storage/coordination и HTTP resources;
- Open-Meteo Forecast/Historical, ERA5-Land current/reference и GFS Ensemble adapters;
- unit/contract tests;
- PostgreSQL/Redis integration tests;
- `pg_dump → pg_restore` verification;
- Alembic graph;
- live Open-Meteo, ERA5-Land и GFS Ensemble contracts;
- Telegram Dispatcher flows для основного сценария, ручного обзора и истории рисков.

## Оценка состояния

| Область | Оценка | Комментарий |
|---|---:|---|
| Архитектура слоёв | 8/10 | границы в целом соблюдены; scheduler и core handler перегружены |
| Научная корректность | 7/10 | формулы ограничены областью применимости; не хватает региональной валидации |
| Хранение и транзакции | 8/10 | async PostgreSQL, миграции, row locks и atomic run/signals |
| Отказоустойчивость | 7/10 | leases/retry/cache есть; нет circuit breaker и измеримых provider metrics |
| Telegram UX | 7/10 | короткий основной flow, ручной обзор и история; нет quiet hours/digest |
| CI и тестирование | 8/10 | сильные unit/integration/live gates; mypy и bandit пока не запускаются |
| Эксплуатационная готовность | 5/10 | нет clean-host, real Telegram и station evidence |

## Сильные стороны

### 1. Научные guardrails встроены в код

- наблюдения, реанализ, прогноз и климатическая база не смешиваются;
- текущий локальный день не считается завершённым прошлым;
- сезонный ГТК скрывается при неполном ряду;
- ET₀ не называется фактической ET культуры или дозой полива;
- `P−ET₀` не называется влагозапасом;
- сырая доля ансамбля `k/n` не называется откалиброванной вероятностью;
- CAPE не выдаётся за прогноз града;
- неполный ансамбль не превращается в «риска нет».

### 2. Критические операции имеют проверяемую семантику

- user/field/season mutations выполняются транзакционно;
- scheduler использует token-checked renewable lease;
- I/O отменяется после потери lease;
- accepted risk run и его signals сохраняются до Telegram side effect;
- неоднозначная внешняя доставка представлена состоянием `sending`;
- повторный run идемпотентен по `field_id + model + retrieved_at`.

### 3. Release engineering заметно выше среднего для небольшого бота

- release содержит код, миграции и systemd units;
- activation проверяется по service state и heartbeat;
- failed activation возвращает код и units предыдущего release;
- backup restore проверяется в CI;
- provider contracts вынесены в отдельные live workflows.

## Сложные участки

### A. `src/bot/scheduler.py`

Файл объединяет:

- регистрацию APScheduler jobs;
- timezone scheduling;
- выбор notification targets;
- provider orchestration;
- domain calculation;
- persistence run/signals;
- delivery state machine;
- Redis deduplication;
- Telegram side effects;
- retention cleanup;
- legacy deterministic frost path;
- daily digest.

Это главный центр операционной сложности. Добавлять туда новые риски, quiet hours или digest напрямую не следует.

**Минимальное упрощение:** вынести только `run_weather_risk_cycle(...)` в `src/application/risk_monitoring.py`. Scheduler должен оставить cron registration и вызов application service. Не создавать универсальный job framework.

### B. `src/bot/handlers/core.py`

Один Router содержит onboarding, поля, координаты, культуры, сезон, фазу и отчёт. Файл труднее читать и тестировать, чем отдельные feature routers.

**Минимальное упрощение:** разделить на:

- `handlers/start.py`;
- `handlers/fields.py`;
- `handlers/season.py`;
- `handlers/report.py`.

Общие helper-функции оставить локальными, не вводить базовые handler-классы.

### C. Терминологический долг `frost_alerts_enabled`

Поле БД и callback `set_frost` теперь управляют общим multi-hazard monitor. Название вводит разработчика в заблуждение и увеличивает риск ошибочных изменений.

**Рекомендация:** одна совместимая Alembic migration:

1. добавить `weather_risk_alerts_enabled`;
2. скопировать значения;
3. перевести код;
4. удалить legacy column в следующем release после проверки.

Не поддерживать оба имени бессрочно.

### D. Transitional columns в `users`

`latitude`, `longitude`, `selected_crop`, `daily_digest` сохранены ради миграционной совместимости, хотя source of truth уже находится в `fields` и `crop_seasons`.

**Рекомендация:** после подтверждения production upgrade удалить transitional columns одной миграцией и соответствующий fallback-код.

### E. Синхронный HTTP внутри executor

Open-Meteo adapters используют synchronous client/cache через `asyncio.to_thread`. При текущей нагрузке это допустимый компромисс, но усложняет cancellation, метрики и общий connection management.

**Рекомендация:** не переписывать немедленно. Сначала добавить latency/error/cache metrics. Переходить на единый async client только при подтверждённом bottleneck или проблемах shutdown/cancellation.

## Слабые места и риски

### P0 — эксплуатационные

1. Нет clean Debian 12 install/reboot/update/forced rollback evidence.
2. Нет real Telegram smoke для нескольких пользователей и полей.
3. Нет Astra Linux acceptance.
4. Нет утверждённого screening-only регламента и резервного канала критических предупреждений.
5. Telegram API не позволяет доказать absolute exactly-once delivery.

### P1 — качество сервиса

1. Нет quiet hours и risk digest.
2. Нет provider latency/error/cache/fallback metrics.
3. Нет circuit breaker и stale-cache age в пользовательском сообщении.
4. Поля обрабатываются последовательно; при росте числа полей цикл станет длинным.
5. Delivery state обновляется отдельной транзакцией на каждый сигнал.
6. Retention запускается opportunistically в weather job, а не независимой ежедневной задачей.

Текущие пункты 4–6 не требуют оптимизации до появления измеримой нагрузки.

### P1 — качество вероятностных данных

Журнал сохраняет только сигналы выше notification threshold. Этого достаточно для UX «усиливается/ослабевает», но недостаточно для unbiased Brier/reliability analysis: нужны также значения ниже порога и фактические наблюдения.

**Рекомендация:** перед калибровкой добавить компактную таблицу daily evaluations либо расширить signals так, чтобы хранить все `risk_type × event_date`, а не только alerts. Не хранить полный DataFrame членов ансамбля в PostgreSQL без отдельного обоснования.

### P2 — научные ограничения

- crop/phase-specific damage thresholds не валидированы;
- GDD `Tbase/Tupper` требуют versioned sources по культуре/региону/сорту;
- локальная FAO-56 Penman–Monteith не реализована;
- нет validated `Kc/Ks` и root-zone water balance;
- нет station ingestion и bias correction;
- нет SoilGrids, Sentinel-2/MODIS production adapters;
- нет специализированной модели града или болезней.

## CI и качество кода

В `requirements-dev.txt` присутствуют `mypy` и `bandit`, но текущий workflow запускает только Ruff и `compileall` перед тестами.

Рекомендуемый порядок без «большого взрыва»:

1. включить `mypy` только для `src/domain`, `src/application/ports` и новых typed DTO;
2. постепенно расширять область после устранения ошибок;
3. добавить `bandit -q -r src -x src/rag` либо явно документированный набор исключений;
4. добавить dependency scan отдельным non-blocking job, затем сделать blocking после стабилизации;
5. сохранять pytest failure logs как artifact — это сократит диагностику CI.

## Производительность

Оптимизация нужна только после метрик. Предлагаемый порядок:

1. измерить длительность provider fetch, DB persistence, Telegram send и полного field cycle;
2. добавить bounded concurrency для полей, например 3–5 задач, сохранив общий provider semaphore;
3. коалесцировать запросы для близких/одинаковых координат только при фактических дублях;
4. batch-update delivery states только если число сообщений существенно вырастет;
5. при росте истории добавить индекс/partitioning только после анализа query plan.

Не рекомендуется сейчас:

- Kafka/RabbitMQ;
- отдельные микросервисы;
- CQRS/event sourcing;
- универсальный repository framework;
- хранение полного ансамбля в JSONB «на всякий случай»;
- переписывание всего HTTP-слоя без метрик.

## Приоритетный roadmap

### Следующий вертикальный срез

**Quiet hours + risk digest**:

- настройки на уровне поля;
- режимы `immediate`, `digest`, `high_only`;
- одно сообщение на цикл вместо серии;
- локальное delivery window;
- запрет отправки уже просроченного события;
- DST/timezone tests.

### Затем

1. clean-host и real Telegram acceptance;
2. provider observability и circuit breaker;
3. station ingestion и forecast/observation matching;
4. calibration metrics;
5. окно полевых работ;
6. почвенно-водный контур;
7. спутниковый мониторинг.

## Критерий следующего релиза

- `main` и Alembic head устанавливаются на чистый Debian 12;
- service стартует после reboot;
- два пользователя и несколько полей проходят реальный Telegram flow;
- журнал показывает минимум два последовательных запуска;
- quiet hours/digest не создают повторный или просроченный alert;
- provider outage отображается как деградация данных;
- station comparison protocol утверждён;
- документация совпадает с production-кодом.
