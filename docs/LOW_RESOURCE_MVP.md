# Эксплуатация MVP на слабом сервере

Дата актуализации: **2026-07-27**.

## Назначение профиля

Профиль по умолчанию сохраняет функции, необходимые для рабочего агрометеорологического Telegram-бота:

- несколько полей и отдельный сезон каждого поля;
- геолокация и ручные координаты;
- культура, дата сезона и наблюдаемая фаза;
- оперативный Open-Meteo Forecast и ограниченная сезонная история;
- ГДД, сезонный ГТК, осадки, provider ET₀ и накопленные показатели;
- ручной и фоновый GFS Ensemble screening погодных рисков;
- PostgreSQL-history сигналов;
- Redis FSM, блокировки scheduler и защита от повторной доставки;
- автоматическое обновление с проверкой GitHub Actions и откатом.

По умолчанию отключены ресурсоёмкие необязательные функции:

```dotenv
RAG_ENABLED=false
INSTALL_RAG_PROFILE=0
CLIMATE_REFERENCE_ENABLED=false
```

Отключение `CLIMATE_REFERENCE_ENABLED` не отключает оперативный прогноз, сезонную историю, ГДД, ГТК, ET₀ или погодные риски. Оно исключает только два больших запроса ERA5 для многолетнего сравнения 1991–2020.

## Минимальная установка

Поддерживаемый путь — Debian 12 или совместимая система с Python 3.11+ и systemd.

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot

sudo install -m 600 /dev/null /root/cropbot-token
sudo editor /root/cropbot-token
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

Скрипт устанавливает только runtime-компоненты MVP:

```text
Python + venv
PostgreSQL client/server
Redis server
Git, CA certificates, OpenSSL, util-linux
```

GDAL, компилятор, RAG-модели и спутниковые библиотеки в базовый профиль не устанавливаются.

После установки должны быть активны:

```bash
sudo systemctl is-active crop-forecast-bot.service
sudo systemctl is-enabled crop-forecast-bot.service
sudo systemctl is-active crop-forecast-bot-update.timer
sudo systemctl is-enabled crop-forecast-bot-update.timer
```

Полная проверка:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

## Что проверяется при запуске

Перед `READY=1` выполняются:

1. валидация environment;
2. подключение к PostgreSQL;
3. соответствие Alembic revision текущему коду;
4. подключение к Redis;
5. проверка writable runtime paths;
6. реальный Telegram `getMe` с установленным токеном;
7. регистрация команд;
8. запуск scheduler.

Heartbeat появляется только после успешной Telegram-проверки. Неверный токен или недоступный Telegram API не проходят release healthcheck.

CI дополнительно выполняет офлайн-проверку:

```bash
python -m src.bot.main --startup-smoke
```

Она собирает production Router graph, PostgreSQL/Redis storage, coordination и scheduler, но не обращается к Telegram.

## Расчёты по сохранённым полям

Источник полей — PostgreSQL `fields` и активный `crop_seasons` каждого поля.

После здорового запуска бот через 120 секунд выполняет один проход по всем полям, у которых включены погодные предупреждения. Затем ансамблевый scheduler продолжает работу по штатному расписанию. Redis lease исключает параллельный запуск двух workers, а deduplication не допускает повторное сообщение о том же состоянии.

Активное поле влияет только на ручную навигацию Telegram. Фоновый расчёт не ограничивается одним активным полем.

Ежедневный агроотчёт формируется только для полей, где он явно включён. По умолчанию он выключен, чтобы не расходовать API и CPU без запроса пользователя.

## Автоматическое обновление

Timer проверяет `main` каждые 15 минут с небольшим случайным сдвигом:

```bash
systemctl list-timers crop-forecast-bot-update.timer
```

Последовательность:

```text
git ls-remote main
→ SHA не изменился: завершение без clone и pip
→ новый SHA: проверка GitHub Actions
→ CI pending/failed/API недоступен: оставить текущий release
→ CI green: shallow clone точного main
→ повторная проверка SHA
→ shared virtualenv или установка изменённых dependencies
→ backup PostgreSQL
→ Alembic upgrade
→ runtime preflight
→ atomic activation
→ Telegram + heartbeat healthcheck
→ при ошибке rollback
```

Обязателен успешный push-run workflow `ci.yml` для точного SHA `main`. Если для этого SHA запущен `provider-smoke.yml`, он также должен завершиться успешно.

Для публичного репозитория токен GitHub необязателен. При необходимости можно задать read-only token:

```dotenv
GITHUB_API_TOKEN=
```

Отключение автоматического обновления:

```dotenv
AUTO_UPDATE_ENABLED=false
```

После изменения:

```bash
sudo systemctl disable --now crop-forecast-bot-update.timer
```

Повторное включение:

```bash
sudo systemctl enable --now crop-forecast-bot-update.timer
```

Сервер, установленный старой версией проекта, нужно один раз перевести на новый release вручную:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
sudo systemctl enable --now crop-forecast-bot-update.timer
```

После этого последующие обновления используют green-CI gate.

## Экономия диска и времени обновления

Virtualenv хранится отдельно от release и определяется содержимым requirements и minor-версией Python. Пока зависимости не изменились, новый release использует уже проверенный environment и не выполняет повторный `pip install`.

По умолчанию сохраняются:

```text
2 code releases
3 PostgreSQL backups
только virtualenv, на который ссылается сохранённый release
```

Текущий и предыдущий release не удаляются.

## Ограничение ресурсов

Runtime использует:

```dotenv
BLOCKING_IO_WORKERS=2
```

Для BLAS/OpenMP задан один поток. Systemd применяет пониженные CPU/IO weights, `TasksMax=64` и мягкий порог `MemoryHigh=384M`.

`MemoryHigh` — сигнал pressure management, а не обещание фиксированного расхода и не жёсткий лимит. `MemoryMax` намеренно не задаётся: кратковременный расчёт pandas не должен приводить к ненужному перезапуску.

PostgreSQL и Redis не удалены из MVP, поскольку они обеспечивают:

- сохранение нескольких полей и сезонов;
- restart-safe FSM;
- межпроцессные scheduler leases;
- deduplication уведомлений;
- историю сигналов и миграции.

Однопроцессный SQLite/MemoryStorage вариант расходовал бы меньше памяти, но не удовлетворял бы требованиям надёжного автоматического обновления и восстановления после перезапуска.

## Диагностика

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
sudo journalctl -u crop-forecast-bot -n 200 --no-pager
sudo journalctl -u crop-forecast-bot-update -n 200 --no-pager
sudo systemctl list-timers crop-forecast-bot-update.timer
```

Ручная проверка наличия обновления:

```bash
sudo systemctl start crop-forecast-bot-update.service
```

Ручной откат:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

## Критерии исправной установки

- `crop-forecast-bot.service` активен;
- heartbeat свежий;
- Alembic current совпадает с head;
- PostgreSQL и Redis доступны;
- Telegram `getMe` пройден до readiness;
- update timer включён;
- установленный unit совпадает с активным release;
- после тестового перезапуска сохранённые поля остаются в БД;
- startup field check и плановый scheduler не создают дубликаты сообщений;
- при failed CI или failed activation текущий рабочий release не заменяется.
