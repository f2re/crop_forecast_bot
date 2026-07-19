# Глубокий аудит Crop Forecast Bot

Дата: **2026-07-19**  
Проверяемая ветка: `main` + вертикальный срез PR #43.

## Резюме

Проект находится в состоянии **code-level полевого пилота**. Базовая архитектурная миграция завершена: один aiogram 3.x runtime, PostgreSQL/Alembic, Redis FSM и coordination, typed provider contracts, агрометеорологический domain-layer, фоновые задания и проверяемый release process.

После текущего среза продукт умеет:

- хранить несколько полей и отдельный сезон каждого поля;
- выдавать оперативный агроотчёт;
- выполнять ансамблевый multi-hazard screening;
- сохранять историю модельных сигналов;
- показывать усиление/ослабление риска;
- объединять риски в один digest;
- учитывать локальные тихие часы и режим чувствительности;
- явно различать отсутствие данных и отсутствие сигнала.

Статус **«готов к самостоятельным критическим решениям в поле» не подтверждён**. Главные незакрытые области — реальная эксплуатационная приёмка, локальная валидация, журнал фактических наблюдений и независимый официальный канал опасных явлений.

## Оценка зрелости

| Область | Оценка | Вывод |
|---|---:|---|
| Архитектура слоёв | 8/10 | основные границы соблюдены; два крупных модуля перегружены |
| Научные guardrails | 8/10 | claims ограничены; не хватает региональной валидации |
| Хранение и транзакции | 8/10 | async PostgreSQL, Alembic, row locks, atomic runs/signals |
| Отказоустойчивость | 7/10 | leases, retry и cache есть; нет circuit breaker и метрик |
| Telegram UX | 8/10 | короткий flow, ручной обзор, история, digest и quiet hours |
| CI и тестирование | 8/10 | unit/integration/live gates сильные; typing/security gates частичные |
| Эксплуатационная готовность | 5/10 | отсутствуют clean-host и real Telegram evidence |
| Полевая доказательность | 5/10 | нет наблюдений пользователя, станции и calibration dataset |

## Подтверждённые сильные стороны

### 1. Архитектурный контур

- один entrypoint `python -m src.bot.main`;
- Telegram handlers не содержат основных метеорологических формул;
- provider I/O скрыт typed ports/DTO;
- PostgreSQL является source of truth;
- Redis используется для FSM, callback idempotency, leases и deduplication;
- startup/shutdown закрывает bot session, storage, DB, coordination и HTTP resources;
- schema revision проверяется до запуска runtime.

### 2. Научная честность

- `reanalysis`, `operational_past`, `forecast` и climate reference не смешиваются;
- текущий локальный день не считается завершённым прошлым;
- сезонный ГТК скрывается при неполном непрерывном ряду;
- provider ET₀ не называется фактической ET культуры;
- `P−ET₀` не называется влагозапасом или дозой полива;
- сырая доля GFS Ensemble `k/n` не называется откалиброванной вероятностью;
- CAPE не выдаётся за прогноз грозы или града;
- неполный ансамбль не превращается в вывод «риска нет»;
- климатическое сравнение использует одну фиксированную модель и общий полный период по температуре, осадкам и ET₀.

### 3. Надёжность и release engineering

- renewable token-checked Redis leases;
- отмена защищённого I/O после потери ownership;
- callback idempotency;
- accepted risk run сохраняется до Telegram side effect;
- неоднозначная доставка представлена состоянием `sending`;
- повтор provider run идемпотентен;
- versioned release объединяет код, migrations и systemd units;
- failed activation возвращает предыдущий код и units;
- CI выполняет `pg_dump → pg_restore`;
- live contracts проверяют Open-Meteo operational, homogeneous climate и GFS Ensemble.

## Найденные и устранённые дефекты текущего аудита

### 1. Устаревший Open-Meteo model alias

Generic Forecast API перестал принимать явное `models=auto`. Адаптер теперь не передаёт этот параметр и использует штатный Best Match по умолчанию. Metadata показывает `best_match`, не выдумывая конкретный model run.

### 2. Несогласованный климатический хвост

Температура, осадки и ET₀ могут появляться с разной задержкой. Ранее частично заполненный хвост мог попадать в current climate DTO. Теперь используется только непрерывный общий prefix, полный одновременно по `t_mean`, `precip_sum` и `et0_sum`.

### 3. Неполный pure ERA5-Land variable contract

Pure ERA5-Land endpoint не обеспечивает полный набор переменных, необходимый для однородного совместного сравнения осадков и ET₀. Current/reference переведены на одну фиксированную ERA5-конфигурацию. Это снижает номинальное пространственное разрешение, но устраняет смешение моделей и неполный водный ряд.

### 4. Недостаточная диагностика CI

Pytest output теперь сохраняется как artifact для unit и integration runs. Это сокращает диагностику реальных CI failures и делает regression evidence воспроизводимым.

## Сложные участки кода

### A. `src/bot/scheduler.py`

Файл объединяет:

- APScheduler registration;
- timezone logic;
- target selection;
- provider orchestration;
- domain calculations;
- persistence;
- delivery planning;
- Redis deduplication;
- Telegram side effects;
- delivery state updates;
- retention;
- legacy frost path;
- daily agro digest.

Это главный центр операционной сложности.

**Минимальное исправление:** вынести только `run_weather_risk_cycle(...)` в `src/application/risk_monitoring.py`. Scheduler должен регистрировать cron и вызывать service. Универсальный job framework, event bus или task queue пока не нужны.

### B. `src/bot/handlers/core.py`

Один Router содержит onboarding, поля, координаты, культуры, сезон, фазу и отчёт.

**Минимальное исправление:** разделить на feature routers:

```text
handlers/start.py
handlers/fields.py
handlers/season.py
handlers/report.py
```

Не создавать базовые handler-классы и собственный routing framework.

### C. Optional RAG path

`handlers/rag.py` выполняет часть weather orchestration и вызывает синхронные RAG/LLM-компоненты из Telegram path. Возможные проблемы:

- блокировка event loop тяжёлыми embedding/vector operations;
- отсутствие единого application service;
- неодинаковые timeout/retry contracts;
- риск некорректного HTML output;
- слабая наблюдаемость источников и latency.

**Рекомендация:** оставить RAG optional и скрытым по feature flag. Перед расширением:

1. создать `application/advisor.py`;
2. выполнять тяжёлые sync операции через bounded executor;
3. ввести явные timeout и shutdown;
4. экранировать Telegram HTML;
5. ограничить число и длину источников;
6. запретить совет без retrieved source.

### D. Терминологический долг

`frost_alerts_enabled` и callbacks `set_frost` теперь управляют общим multi-hazard monitor.

**Рекомендация:** совместимая миграция:

1. добавить `weather_risk_alerts_enabled`;
2. перенести значения;
3. перевести код и callbacks;
4. удалить legacy column после подтверждённого production upgrade.

Не поддерживать оба имени бессрочно.

### E. Transitional columns в `users`

`latitude`, `longitude`, `selected_crop`, `daily_digest` больше не являются source of truth.

**Рекомендация:** удалить после clean production migration evidence вместе с fallback-кодом. Не объединять это с продуктовой фичей.

### F. Синхронный HTTP в executor

Open-Meteo adapters используют sync client/cache через `asyncio.to_thread`.

При текущей нагрузке это разумный компромисс. Переписывать HTTP-слой без метрик не следует. Сначала измерить latency, cancellation и thread-pool saturation.

## Слабые места

### P0 — эксплуатационные

1. Нет clean Debian 12 deploy/reboot/update/forced rollback evidence.
2. Нет real Telegram smoke для нескольких пользователей и полей.
3. Нет Astra Linux acceptance.
4. Нет screening-only регламента для оператора и пользователя.
5. Нет независимого официального канала критических предупреждений.
6. Telegram API не позволяет доказать absolute exactly-once delivery.

### P1 — наблюдаемость

1. Нет provider latency/error/cache/fallback metrics.
2. Нет circuit breaker.
3. Пользователь не видит stale-cache age.
4. Нет административного provider status.
5. Поля обрабатываются последовательно; масштабируемость не измерена.

### P1 — качество вероятностных данных

Risk history хранит threshold-crossing events. Этого достаточно для UX trend, но недостаточно для unbiased verification.

Для Brier/reliability нужны:

- below-threshold evaluations;
- exact lead time;
- model/source/retrieval metadata;
- фактическое наблюдение;
- matching policy;
- отдельные выборки по региону, сезону и риску.

Не следует хранить полный ensemble DataFrame в PostgreSQL «на всякий случай». Достаточна компактная daily evaluation table.

### P1 — геометрия поля

Сейчас поле представлено одной точкой. Это приемлемо для point forecast, но недостаточно для корректного спутникового мониторинга и пространственной неоднородности.

Перед Sentinel-2 необходимо добавить polygon/multipolygon geometry и проверку площади/валидности.

## Функции с наибольшей пользой

Оценка: польза 1–5, сложность 1–5, научный риск 1–5.

| Функция | Польза | Сложность | Научный риск | Приоритет |
|---|---:|---:|---:|---|
| Полевой журнал наблюдений и операций | 5 | 2 | 1 | P0/P1 |
| Окно выполнения полевых работ | 5 | 3 | 2 | P1 |
| Официальные CAP-предупреждения | 5 | 3 | 1 | P1 |
| Импорт локальной метеостанции | 5 | 4 | 2 | P1 |
| Проверка качества прогноза по lead time | 4 | 4 | 2 | P1 |
| Provider status/freshness | 4 | 2 | 1 | P1 |
| SoilGrids-контекст почвы | 4 | 3 | 3 | P2 |
| Полигон поля + Sentinel-2 NDVI/LAI | 4 | 5 | 3 | P2 |
| FAO-56 + root-zone water balance | 5 | 5 | 5 | P2 после входных данных |
| GloFAS/речной паводок | 3 | 3 | 3 | P2, только рядом с реками |
| Disease infection windows | 4 | 5 | 5 | только pathogen-specific |
| Валидированный прогноз града | 4 | 5 | 5 | отдельный исследовательский поток |

## Рекомендуемый следующий вертикальный срез

### Полевой журнал

Это наиболее простой и фундаментальный следующий шаг.

Пользователь фиксирует для поля:

- дату и локальное время;
- фактическую фазу;
- выполненную операцию;
- полив, мм или неизвестно;
- измеренные осадки;
- минимальную/максимальную температуру станции;
- наблюдаемое повреждение;
- свободную заметку;
- optional photo/file reference без анализа изображения на первом этапе.

Минимальная схема:

```text
field_observations
- id
- field_id
- observed_at
- observation_type
- numeric_value
- unit
- note
- source
- created_at
```

Первые типы:

```text
phase
operation
irrigation
rain_gauge
station_tmin
station_tmax
damage
note
```

Почему это приоритетнее нового индекса:

- создаёт фактический контекст для рекомендаций;
- даёт данные для проверки model bias;
- позволяет оценивать пользу уведомлений;
- поддерживает будущий water balance;
- помогает фермеру вести историю поля даже при недоступности провайдера;
- не требует недоказанной модели.

Definition of Done:

1. add/list/delete observation для активного поля;
2. PostgreSQL + Alembic;
3. restart-safe FSM;
4. локальное время поля;
5. unit validation значений и единиц;
6. Telegram scenario tests;
7. экспорт CSV позже отдельным срезом;
8. никакой автоматической интерпретации повреждения без модели.

## Следующий после журнала срез

### Окно полевых работ

Отвечает на ограниченный вопрос: когда погодные условия менее неблагоприятны для выполнения выбранной операции.

Первый набор операций:

- общие полевые работы;
- внесение/опрыскивание — только погодное окно, без доз и обхода этикетки;
- уборка;
- полив;
- выезд тяжёлой техники — только предварительный screening.

Используемые данные:

- осадки до и после окна;
- вероятность/ensemble spread осадков;
- средний ветер и порывы;
- температура;
- относительная влажность или VPD;
- предшествующие осадки;
- daylight/local time;
- пользовательская операция.

Вывод должен объяснять каждое ограничение. Не использовать единый «индекс пригодности» без прозрачных составляющих.

## Официальные предупреждения

Модельный сигнал и официальный warning должны отображаться отдельно:

```text
Официальное предупреждение
Модельный ранний сигнал
```

CAP-интеграция должна быть provider adapter по стране/региону, с сохранением identifier, issuer, severity, area и effective/expires. Официальное предупреждение не смешивается с GFS member fraction.

## Почвенно-водный контур

### SoilGrids

Можно добавить как контекст, а не как точное лабораторное измерение:

- texture fractions;
- bulk density;
- organic carbon;
- coarse fragments;
- доступные глубины;
- uncertainty/quantiles;
- явный no-data/ocean guard;
- долгий cache.

### Root-zone water balance

Не реализовывать как следующий быстрый срез. Нужны:

- validated `Kc` по культуре и фазе;
- `Ks`;
- глубина корней;
- почвенная влагоёмкость;
- начальный запас;
- полив пользователя;
- runoff/infiltration assumptions;
- локальная FAO-56 или согласованный provider ET₀;
- полевая проверка.

## Спутниковый мониторинг

Необходимо:

1. polygon field geometry;
2. Sentinel-2 L2A;
3. SCL/cloud/water/shadow masks;
4. minimum valid pixel coverage;
5. собственная временная база поля;
6. повторный сигнал на нескольких наблюдениях;
7. отсутствие универсального NDVI threshold;
8. fallback на MODIS/Copernicus только с явным более грубым разрешением.

Не использовать прекращённый продукт только потому, что он упомянут в старой документации.

## CI и безопасность

В `requirements-dev.txt` присутствуют `mypy` и `bandit`, но они не являются полноценными blocking gates.

Порядок внедрения:

1. mypy для `src/domain`, `src/application/ports`, DTO и новых modules;
2. исправление ошибок;
3. расширение области;
4. Bandit с явным набором исключений;
5. dependency scan сначала non-blocking;
6. затем blocking после стабилизации;
7. pytest logs сохранять как artifacts — реализовано в текущем срезе.

## Производительность

Сначала метрики, затем оптимизация:

1. provider fetch duration;
2. DB persistence duration;
3. Telegram send duration;
4. total field cycle;
5. cache hit/stale age;
6. queueing/thread-pool saturation.

Только после измерений:

- bounded concurrency 3–5 полей;
- batch delivery-state update;
- coordinate request coalescing;
- index/query-plan tuning;
- отдельный retention job.

## Что не следует строить сейчас

- Kafka/RabbitMQ;
- микросервисы;
- CQRS/event sourcing;
- универсальный rules engine;
- собственный workflow framework;
- full ensemble JSONB storage;
- generic AI yield prediction;
- генератор доз препаратов/удобрений;
- переписывание всего HTTP-слоя без метрик;
- автоматическую фенофазу по неподтверждённым GDD thresholds.

## Приоритетный roadmap

### P0

1. clean-host Debian 12 deploy/reboot/update/rollback;
2. real Telegram smoke;
3. operator screening protocol;
4. station comparison protocol;
5. полевой журнал — первый следующий кодовый срез.

### P1

1. окно полевых работ;
2. official CAP warnings;
3. provider metrics/status/stale age;
4. station ingestion и forecast matching;
5. below-threshold daily evaluations;
6. совместимое переименование `frost_alerts_enabled`;
7. разделение scheduler/core handler;
8. постепенные mypy/Bandit gates.

### P2

1. field polygons;
2. SoilGrids context;
3. Sentinel-2 L2A monitoring;
4. FAO-56/root-zone balance;
5. GloFAS screening;
6. pathogen-specific disease models;
7. отдельная hail research/validation track.

## Итог

Проекту не нужна новая платформа. Наибольший прирост качества даст сочетание:

```text
эксплуатационная приёмка
+ фактические полевые наблюдения
+ объяснимое окно работ
+ официальный warning layer
+ измеримая provider observability
```

Следует продолжать небольшими вертикальными срезами, где каждая функция проходит Telegram flow, DB/API contracts, tests и документацию до слияния.
