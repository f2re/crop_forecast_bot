# Эксплуатация MVP на слабом сервере

Дата актуализации: **2026-07-31**.

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

Поддерживаемый путь — Debian 12, Ubuntu 22.04 или совместимая система с Python 3.10+ и systemd.

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
→ backup PostgreSQL только при изменении Alembic head
→ Alembic upgrade
→ runtime preflight
→ atomic activation
→ Telegram + heartbeat healthcheck
→ при ошибке rollback
```

Обязателен успешный push-run workflow `ci.yml` для точного SHA `main`. Если для этого SHA зарегистрированы `provider-smoke.yml` или `ensemble-provider-smoke.yml`, они также должны завершиться успешно.

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

Virtualenv хранится отдельно от release и определяется содержимым requirements, версией layout и minor-версией Python. Он создаётся сразу по окончательному пути: console-script shebang не ломается перемещением каталога. Marker `.cropbot-complete` не позволяет повторно использовать оборванную установку зависимостей.

Пока fingerprint не изменился, новый release использует уже проверенный environment и не выполняет повторный `pip install`.

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

### `alembic: Permission denied` во время первого deploy

В release `2ad11ae372c6` причина состояла из двух ошибок установщика:

1. `umask 0027`, применённый при создании `/etc/crop-forecast-bot.env`, оставался активным и делал root-owned virtualenv недоступным пользователю `cropbot`;
2. virtualenv создавался под временным именем и затем перемещался, хотя console scripts содержат абсолютный shebang.

Проверка старого release:

```bash
release=/opt/crop-forecast-bot/releases/20260731T131352Z-2ad11ae372c6

namei -l "$release/.venv/bin/alembic"
readlink -f "$release/.venv"
stat -c '%A %U:%G %n' \
  /var/lib/crop-forecast-bot \
  /var/lib/crop-forecast-bot/venvs \
  "$(readlink -f "$release/.venv")" \
  "$release/.venv/bin/python" \
  "$release/.venv/bin/alembic"
head -n 1 "$release/.venv/bin/alembic"
findmnt -no TARGET,OPTIONS -T "$release/.venv/bin/alembic"

sudo -u cropbot "$release/.venv/bin/python" -c \
  'import sys, alembic; print(sys.executable, alembic.__version__)'
```

`head -n 1` у повреждённого launcher обычно показывает удалённый путь `.staging-…/bin/python`. Отсутствие `x` на каталогах для `cropbot` или опция `noexec` также видны командами выше.

После попадания исправления в `main` достаточно обновить checkout и повторить deploy. Новый fingerprint создаёт отдельный исправный virtualenv; старый удалять вручную не требуется:

```bash
git pull --ff-only origin main
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

Для ручной миграции всегда используется module invocation, не console script:

```bash
sudo -u cropbot bash -lc \
  'cd /opt/crop-forecast-bot/current && .venv/bin/python -m alembic current'
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
