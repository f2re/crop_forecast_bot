# 🌾 Crop Forecast Bot

Telegram-бот для проверяемой агрометеорологической оценки:

```text
поле → культуры → дата и фаза → отчёт → погодные сигналы → история → уведомления
```

[![CI](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml/badge.svg)](https://github.com/f2re/crop_forecast_bot/actions/workflows/ci.yml)

**Стек:** Python 3.10+, aiogram 3.x, PostgreSQL, Redis, Alembic, APScheduler и systemd. Docker не используется.

> Пропуск данных не заменяется эвристикой. «Недостаточно данных» и «риск не выявлен» — разные состояния.

## MVP по умолчанию

Базовый production-профиль рассчитан на слабый сервер и оставляет функции, необходимые фермеру или агроному:

- несколько сохранённых полей;
- геолокация и ручные координаты;
- несколько культур на одной координатной точке;
- отдельные дата посева и фактическая фаза каждой культуры;
- inline-календарь с ручным вводом как резервом;
- оперативный Open-Meteo Forecast и ограниченная сезонная история;
- ГДД, сезонный ГТК, provider ET₀, `P−ET₀`, накопленные осадки и сухие серии;
- GFS Ensemble screening холода, жары, сильных осадков, ветра и конвективной среды;
- понятный ручной обзор `/risks` и история `/history`;
- фоновые расчёты всех полей с включёнными предупреждениями;
- режимы доставки `immediate / digest / high_only` и тихие часы;
- защита Telegram HTML с повтором сообщения обычным текстом при ошибке entities;
- PostgreSQL-history, Redis FSM и защита от повторных сообщений;
- автоматическое обновление зелёной ветки `main` с откатом.

В MVP отключены необязательные тяжёлые возможности:

```dotenv
RAG_ENABLED=false
INSTALL_RAG_PROFILE=0
CLIMATE_REFERENCE_ENABLED=false
```

Отключение многолетнего ERA5-сравнения не отключает оперативную погоду, сезонную историю, ГДД, ГТК, ET₀ и риски.

Подробный профиль: [`docs/LOW_RESOURCE_MVP.md`](docs/LOW_RESOURCE_MVP.md).

## Пользовательский сценарий

1. Отправьте `/start`.
2. Откройте **«Мои поля»** и добавьте координатную точку.
3. В разделе **«Культуры поля»** добавьте томат, картофель или другие культуры этой точки.
4. Выберите культуру, для которой нужен отчёт.
5. Укажите дату посева через календарь и фактически наблюдаемую фазу.
6. Откройте **«Агроотчёт»**, **«Погодные условия»** или **«История сигналов»**.
7. В **«Уведомлениях»** выберите режим и тихие часы.

Погодные данные общие для координатной точки. Дата, фаза и сезонные накопления относятся к выбранной культуре. Активное поле используется для ручных действий; фоновый scheduler обрабатывает **все** сохранённые поля с включёнными предупреждениями.

### Команды

| Команда | Назначение |
|---|---|
| `/start` | главное меню и профиль активного поля |
| `/crops` | культуры активного поля |
| `/report` | агроотчёт выбранной культуры |
| `/risks` | погодные условия, требующие внимания |
| `/history` | изменение модельных сигналов между запусками |
| `/help` | пользовательская справка |
| `/cancel` | отмена текущего FSM-ввода |

## Фоновые расчёты

После успешного запуска бот:

1. проверяет PostgreSQL, Redis и Alembic revision;
2. проверяет реальный Telegram token через `getMe`;
3. запускает scheduler;
4. через 120 секунд выполняет первый расчёт всех сохранённых alert-enabled fields;
5. продолжает ансамблевый анализ каждые 6 часов.

Redis lease не допускает одновременный запуск двух workers. Принятый risk run сначала сохраняется в PostgreSQL, затем применяется политика доставки. Перезапуск не должен создавать повторное сообщение о том же состоянии.

Ежедневный агроотчёт выполняется только для полей, где пользователь его включил. Он относится к выбранной культуре поля и по умолчанию выключен.

## Как читать погодные сигналы

Используются отдельные варианты NOAA GFS Ensemble через Open-Meteo Ensemble API. Для каждой локальной даты анализируются:

- Tmin воздуха 2 м;
- Tmax воздуха 2 м;
- суточные осадки;
- максимальный порыв ветра 10 м;
- CAPE max.

Сутки принимаются только при достаточном числе вариантов по всем диагностическим переменным. Соседние дни одного явления объединяются в период. Пользователь видит:

- физическое условие: температура, осадки, порыв или CAPE;
- сколько вариантов модели указывает на это условие;
- ожидаемое значение и основной разброс вариантов;
- срок и осторожный приоритет действия;
- источник, покрытие и практическое ограничение.

Число вариантов характеризует согласованность **текущего запуска модели**. Оно не является автоматически вероятностью события, повреждения культуры или потери урожая. Дальний сигнал используется для планирования и должен подтверждаться следующими запусками.

CAPE означает доступную энергию для развития конвекции. Сам по себе CAPE не доказывает грозу или град. Для специализированной оценки дополнительно нужны вертикальный профиль влаги, подъём, CIN, сдвиг ветра, уровень замерзания и краткосрочные наблюдения.

Если на точке несколько культур, бот перечисляет их, но не заявляет одинаковое повреждение: чувствительность зависит от культуры, сорта, фазы, влаги и агротехники. Подробнее: [`docs/FARMER_UX.md`](docs/FARMER_UX.md).

### Доставка рисков

```text
immediate  — новое или существенно изменившееся состояние
digest     — одна обычная сводка в локальные сутки
high_only  — только высокий уровень
```

Тихие часы:

```text
выключены
22:00–07:00
23:00–06:00
```

Уровни `watch/elevated` в тихие часы откладываются. Высокий приоритет текущего модельного сигнала отправляется без ожидания тихих часов или обычного суточного дайджеста.

## Агрометеорологические расчёты

### ГДД

```text
GDDday = max(0, min((Tmax + Tmin) / 2, Tupper) − Tbase)
```

- единицы: `°C·сут`;
- строки до локальной даты сезона исключаются;
- завершённый период и прогнозный прирост считаются отдельно;
- автоматическая фенофаза не определяется.

### ГТК Селянинова

```text
ГТК = 10 × ΣP / ΣTср
```

ГТК публикуется только при заданной дате сезона, завершённых локальных сутках, `Tср > 10°C`, не менее 20 тёплых суток и непрерывном ряде. Прогнозные осадки не входят в сезонный ГТК.

### Осадки и ET₀

Показываются:

- короткая диагностическая разность `P−ET₀`;
- накопленные `ΣP` и provider `ΣET₀`;
- парная `ΣP−ΣET₀`;
- сухие/влажные сутки при пороге 1 мм/сут;
- текущая и максимальная сухая серия;
- Rx1day и ограниченный Rx5day.

ET₀ — эталонная эвапотранспирация, а не фактическая ET культуры. `P−ET₀` не является влагозапасом или дозой полива.

### Многолетнее сравнение

Однородное сравнение текущего сезона с ERA5 1991–2020 остаётся доступным, но отключено в слабом production-профиле:

```dotenv
CLIMATE_REFERENCE_ENABLED=true
```

После изменения перезапустите сервис. Это отдельная реанализная модельная сетка, а не полевая станция, SPI/SPEI или прогноз урожайности.

## Установка без Docker

### Новый сервер

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot

sudo install -m 600 /dev/null /root/cropbot-token
sudo editor /root/cropbot-token
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

Скрипт создаёт пользователя сервиса, PostgreSQL, Redis, environment, миграции, versioned release, systemd service и timer автоматического обновления.

Конфигурация:

```text
/etc/crop-forecast-bot.env
```

### Обновление старой установки

Один раз выполните:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
sudo systemctl enable --now crop-forecast-bot-update.timer
```

После этого новые зелёные коммиты `main` устанавливаются автоматически.

## Безопасное автоматическое обновление

Timer проверяет `main` каждые 15 минут с небольшим случайным сдвигом. Порядок:

```text
git ls-remote
→ SHA не изменился: завершение без clone и pip
→ новый SHA: проверка GitHub Actions
→ pending/failed/API недоступен: оставить текущий release
→ green CI: shallow clone и повторная проверка SHA
→ shared virtualenv или установка изменённых dependencies
→ backup PostgreSQL при изменении схемы
→ Alembic upgrade
→ preflight
→ activation
→ Telegram + heartbeat healthcheck
→ rollback при ошибке
```

Обязателен успешный push-run `ci.yml` для точного SHA `main`. Если для SHA запущен provider smoke, он также обязан завершиться успешно.

Проверка timer:

```bash
sudo systemctl list-timers crop-forecast-bot-update.timer
```

Отключение:

```bash
sudo systemctl disable --now crop-forecast-bot-update.timer
```

Повторное включение:

```bash
sudo systemctl enable --now crop-forecast-bot-update.timer
```

## Ресурсы

Базовый installer не ставит GDAL, compiler toolchain, RAG-модели и спутниковые библиотеки. Inline-календарь и дополнительные культуры не добавляют runtime-зависимостей и не создают отдельный погодный запрос на каждую культуру. Virtualenv повторно используется, пока не изменились Python minor version или requirements.

Runtime по умолчанию:

```dotenv
BLOCKING_IO_WORKERS=2
RISK_HISTORY_RETENTION_DAYS=30
```

BLAS/OpenMP ограничены одним потоком. Systemd применяет мягкий `MemoryHigh=384M`, пониженные CPU/IO weights и `TasksMax=64`. Жёсткий `MemoryMax` не используется, чтобы кратковременный расчёт pandas не приводил к ненужному перезапуску.

PostgreSQL и Redis сохранены, поскольку обеспечивают несколько полей и культур, restart-safe FSM, leases, deduplication, историю и миграции.

## Администрирование

```bash
# Сервис, heartbeat, БД, Redis, release, timer и журнал
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh

# Локальная проверка release
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh

# Реальные Open-Meteo/ERA5 проверки
sudo -u cropbot bash \
  /opt/crop-forecast-bot/current/scripts/verify-production.sh \
  --live-all 55.75 37.62 2026-04-15 wheat

# Проверка восстановления backup
sudo bash \
  /opt/crop-forecast-bot/current/scripts/verify-backup-restore.sh

# Ручное обновление и откат
sudo systemctl start crop-forecast-bot-update.service
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh

# Журналы
sudo journalctl -u crop-forecast-bot -f
sudo journalctl -u crop-forecast-bot-update -f
```

Production entrypoint:

```bash
python -m src.bot.main
```

CI startup-smoke без Telegram-сети:

```bash
python -m src.bot.main --startup-smoke
```

## Проверки разработчика

```bash
pip install -r requirements-dev.txt
ruff check src config alembic tests
python -m compileall -q alembic config src tests
python -m pytest -q -m "not integration"
TEST_DATABASE_URL=... TEST_REDIS_URL=... \
  python -m pytest -q -m integration
python -m alembic heads
```

CI также выполняет ShellCheck, repository policies, production startup smoke, Python 3.10 compatibility, PostgreSQL/Redis integration, backup/restore и live provider contracts.

## Что не заявляется

В production-code нет:

- валидированного прогноза урожайности;
- SPI/SPEI по короткому прогнозу;
- crop/phase damage model;
- откалиброванной вероятности града;
- локального FAO-56 Penman–Monteith;
- validated `Kc/Ks` и root-zone water balance;
- SoilGrids/Sentinel/MODIS production adapters;
- доз препаратов или удобрений без нормативного источника.

## Граница готовности

Code-level flow, CI и live provider contracts проверяются автоматически. До самостоятельного использования для решений с высокой ценой ошибки обязательны:

- clean Debian 12 install/reboot/update/rollback;
- реальный Telegram smoke для нескольких пользователей, полей и культур;
- Astra Linux smoke;
- сравнение с локальной станцией;
- screening-only регламент;
- независимый официальный канал критических предупреждений.

Фактическая матрица: [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md).  
Статус: [`docs/STATUS.md`](docs/STATUS.md).  
План: [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md).  
Эксплуатация слабого сервера: [`docs/LOW_RESOURCE_MVP.md`](docs/LOW_RESOURCE_MVP.md).  
Пользовательская логика: [`docs/FARMER_UX.md`](docs/FARMER_UX.md).
