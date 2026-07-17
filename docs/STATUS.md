# Статус разработки

Дата актуализации: **2026-07-17**.

Текущий вертикальный срез: **ансамблевый мониторинг погодных рисков NOAA GFS через Open-Meteo и строгий сезонный ГТК**. Код, unit/contract tests и методика добавлены в отдельной ветке; полный CI и внешняя полевая приёмка ещё обязательны.

## Production-контур

```text
aiogram 3.x
PostgreSQL + Alembic
Redis FSM / callback idempotency / renewable leases / deduplication
Open-Meteo Forecast + bounded Historical Weather
Open-Meteo GFS Ensemble members
ERA5-Land current season + 1991–2020 reference
APScheduler
systemd + versioned releases + heartbeat + rollback
```

## Подтверждённые возможности

### Telegram и состояние

- [x] один entrypoint `python -m src.bot.main`;
- [x] несколько полей;
- [x] координаты/геолокация, культура, дата сезона и ручная фаза;
- [x] агроотчёт и настройки уведомлений по полю;
- [x] Redis FSM restart;
- [x] replay-safe callbacks;
- [x] race-safe PostgreSQL onboarding;
- [x] controlled PostgreSQL/Redis/Telegram error UX.

### Storage и scheduler

- [x] SQLAlchemy 2 async и обязательный Alembic head;
- [x] `Field` / `CropSeason`;
- [x] row locks и атомарные user/field/season mutations;
- [x] renewable Redis scheduler leases;
- [x] отмена provider/report после lease loss;
- [x] crash/TTL recovery и two-worker tests;
- [x] notification deduplication.

### Агрометеорологические показатели

- [x] typed weather/climate provider contracts;
- [x] раздельные `reanalysis / operational_past / forecast`;
- [x] GDD от локальной даты сезона с crop-specific `Tbase`;
- [x] сезонный ГТК только при явной дате сезона и полном непрерывном ряду;
- [x] прогнозные осадки и отрицательные значения исключены из ГТК;
- [x] ГТК скрывается при пропуске или менее 20 тёплых завершённых суток;
- [x] provider ET₀ и P−ET₀ без подстановки нулей;
- [x] накопленные осадки, ET₀ и парная `ΣP−ΣET₀`;
- [x] сухие/влажные серии и Rx1day/Rx5day с continuity guards;
- [x] ERA5-Land current/reference одной моделью;
- [x] фиксированный reference 1991–2020 и минимум 20 валидных лет;
- [x] descriptive empirical percentiles без выдачи за probability/SPI/SPEI;
- [x] fail-soft climate section.

### Ансамблевые предупреждения

- [x] отдельные члены GFS Ensemble Seamless;
- [x] горизонт до 16 суток;
- [x] Tmin, Tmax, осадки, порывы и CAPE;
- [x] холод, жара, сильные осадки, ветер и конвективная неустойчивость;
- [x] минимум 20 валидных членов для каждого показателя;
- [x] сутки принимаются только при полном покрытии всех пяти рисков;
- [x] вывод `k/n`, P10, медианы, P90 и заблаговременности;
- [x] сырая доля членов не называется откалиброванной вероятностью;
- [x] CAPE не называется прогнозом грозы или града;
- [x] запуск каждые 6 часов;
- [x] dedup по полю/риску/дате/уровню;
- [x] максимум пять наиболее важных сообщений на поле за цикл;
- [x] русская практическая подсказка и научное ограничение в каждом сообщении;
- [x] отдельное закрытие HTTP-сессии при shutdown;
- [x] unit tests расчёта, parser contract, fail-closed coverage, formatter и scheduler dedup.

Методика: `docs/ENSEMBLE_RISK_METHODOLOGY.md`.

### Release engineering

- [x] native deploy/update/rollback/status;
- [x] systemd unit рендерится из точного release;
- [x] failed activation восстанавливает код и unit вместе;
- [x] active + heartbeat verification;
- [x] PostgreSQL backup restore round trip в CI;
- [x] schema/Alembic/core-table fingerprints;
- [x] live provider verification commands и scheduled workflow.

## Научные ограничения

- ГТК теперь требует полного сезонного ряда, но региональные интерпретационные пороги ещё не валидированы.
- Provider ET₀ — reference evapotranspiration, не фактическая ET культуры и не доза полива.
- Tmin воздуха 2 м — screening, не температура растения и не crop damage model.
- GDD-параметры требуют versioned cultivar/region validation.
- ERA5-Land и GFS — модельные поля, не локальная станция.
- Сырая доля ансамбля требует архивной калибровки, прежде чем называться вероятностью.
- Валидированный прогноз града отсутствует.
- SPI/SPEI по короткому прогнозу не реализуются.
- Урожайность, дозы удобрений и препаратов не прогнозируются без проверяемой модели или норматива.

## Что ещё требует внешней среды

- [ ] полный CI текущей ветки;
- [ ] clean Debian 12 deploy и reboot;
- [ ] real Telegram API smoke для двух пользователей и нескольких полей;
- [ ] intentionally failed release на реальном systemd host;
- [ ] Astra Linux smoke;
- [ ] live ensemble provider evidence artifact;
- [ ] сравнение GFS/ERA5-Land/ET₀/ГТК с локальными станциями;
- [ ] проверка полезности и частоты предупреждений с агрономами.

> Telegram Bot API не предоставляет application idempotency key для `sendMessage`. Абсолютный exactly-once результат между внешней отправкой и Redis dedup недоказуем. Бот не должен быть единственным каналом критических предупреждений.

## Ближайшие задачи

### P0

- [ ] пройти полный CI и устранить static/type/integration regressions;
- [ ] выполнить clean-host и Telegram field acceptance;
- [ ] проверить ensemble provider на реальном ответе и сохранить evidence;
- [ ] ввести model-run/retrieval-time в долговременный журнал предупреждений;
- [ ] провести station comparison минимум в нескольких регионах и сезонах.

### P1

- [ ] архив прогнозов и наблюдений для Brier/reliability/ROC/PR/economic value;
- [ ] калибровка по риску, сроку и региону;
- [ ] trend persistence между последовательными запусками;
- [ ] quiet hours и digest режима рисков;
- [ ] stale-cache age, circuit breaker, rate limiter и provider metrics;
- [ ] окно полевых работ и опрыскивания без нарушения этикетки препарата;
- [ ] SoilGrids + рельеф для переувлажнения/проходимости/эрозии;
- [ ] FAO-56 + validated `Kc/Ks` + root-zone water balance;
- [ ] Sentinel-2/MODIS NDVI/LAI с quality masks;
- [ ] GloFAS flood screening;
- [ ] подключение локальной метеостанции и bias correction.

## Готовность

**Code-level:** основной бот, сезонный ГТК и ансамблевый срез реализованы.

**Полевой продукт:** ещё не принят. Для статуса «готов к эксплуатации» обязательны полный CI, real Telegram smoke, clean-host/reboot/rollback, live provider evidence и региональная валидация.
