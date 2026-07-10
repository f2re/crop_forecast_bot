# Crop Forecast Bot

Telegram-бот для оперативной агрометеорологической оценки поля. Production runtime использует **aiogram 3.x**, PostgreSQL, Redis и нативный systemd-сервис.

## Что работает в основном сценарии

1. пользователь задаёт поле геолокацией или координатами;
2. выбирает культуру;
3. получает оперативный отчёт по данным Open-Meteo:
   - температурный риск;
   - ГДД за доступный период;
   - ГТК только при достаточном валидном окне;
   - баланс осадки − ET₀;
   - источник, период и ограничения оценки;
4. может включить ежедневный отчёт;
5. может открыть RAG-советник, если администратор проиндексировал литературу.

Проект **не выдаёт** краткий архив за климатическую норму, эвристику за прогноз урожайности или синтетическую ML-модель за валидированную production-модель.

## Архитектура

```text
handlers -> application services -> domain/agro -> infrastructure
                                           -> Open-Meteo
                                           -> PostgreSQL
                                           -> Redis
                                           -> RAG adapters
```

Единственная точка запуска:

```bash
python -m src.bot.main
```

Legacy `pyTelegramBotAPI` runtime удалён.

## Нативное развёртывание

Поддерживается автоматическая установка на Debian/Ubuntu/Astra-совместимом сервере. Нужны root-доступ, Git и токен Telegram-бота.

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
sudo bash scripts/deploy.sh
```

Первый запуск:

- устанавливает Python, PostgreSQL, Redis и системные библиотеки;
- создаёт системного пользователя `cropbot`;
- создаёт локальную БД и отдельный пароль;
- создаёт защищённый файл `/etc/crop-forecast-bot.env`;
- завершает работу, если токен ещё не задан.

Задайте токен и повторите команду:

```bash
sudo editor /etc/crop-forecast-bot.env
sudo bash scripts/deploy.sh
```

Для полностью неинтерактивной установки можно передать файл с токеном, доступный только root:

```bash
sudo TOKEN_FILE=/root/cropbot-token bash scripts/deploy.sh
```

После preflight скрипт создаёт изолированный release-каталог, virtualenv, проверяет зависимости и runtime, атомарно переключает ссылку `current` и запускает systemd-сервис.

## Эксплуатационные пути

| Путь | Назначение |
|---|---|
| `/opt/crop-forecast-bot/releases/` | неизменяемые версии приложения |
| `/opt/crop-forecast-bot/current` | активная версия |
| `/opt/crop-forecast-bot/previous` | предыдущая версия для отката |
| `/etc/crop-forecast-bot.env` | секреты и runtime-конфигурация |
| `/var/lib/crop-forecast-bot/` | постоянные данные, литература и модели |
| `/var/cache/crop-forecast-bot/` | pip, embeddings и Open-Meteo cache |
| `/var/backups/crop-forecast-bot/` | резервные копии PostgreSQL перед обновлением |

## Управление сервисом

Статус и полная диагностика:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

Логи:

```bash
sudo journalctl -u crop-forecast-bot -f
```

Перезапуск:

```bash
sudo systemctl restart crop-forecast-bot
```

Сервис запускается при загрузке ОС, автоматически перезапускается после аварии и контролируется systemd watchdog. Heartbeat обновляется из event loop; зависший процесс не считается рабочим.

## Обновление

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/update.sh main
```

Обновление выполняется без правки активного каталога:

1. создаётся резервная копия PostgreSQL;
2. новая версия клонируется в отдельный release-каталог;
3. создаётся новый virtualenv;
4. выполняются `pip check`, `compileall`, проверка БД/Redis и writable paths;
5. при наличии Alembic выполняется `alembic upgrade head`;
6. ссылка `current` переключается атомарно;
7. проверяются systemd state и heartbeat;
8. при неуспешном запуске возвращается предыдущая версия.

Ручной откат:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh
```

Откат к конкретной сохранённой версии:

```bash
sudo bash /opt/crop-forecast-bot/current/scripts/rollback.sh \
  /opt/crop-forecast-bot/releases/20260710T120000Z-0123456789ab
```

Схема БД автоматически назад не откатывается. Перед каждым обновлением сохраняется dump; миграции должны оставаться обратно совместимыми либо иметь отдельный проверенный rollback-план.

## Опциональное автоматическое обновление

Таймер устанавливается, но по умолчанию выключен. Включение еженедельной проверки ветки `main`:

```bash
sudo systemctl enable --now crop-forecast-bot-update.timer
systemctl list-timers crop-forecast-bot-update.timer
```

Для production рекомендуется включать таймер только после настройки branch protection и обязательного зелёного CI.

## Конфигурация

Основные переменные:

| Переменная | Назначение |
|---|---|
| `TELEGRAM_BOT_TOKEN` | обязательный токен Telegram |
| `DATABASE_URL` | SQLAlchemy async URL `postgresql+asyncpg://...` |
| `REDIS_URL` | persistent FSM/cache, обязательно для production |
| `SCHEDULER_TIMEZONE` | timezone фоновых задач |
| `HEARTBEAT_FILE` | heartbeat event loop для watchdog/диагностики |
| `OPEN_METEO_CACHE_PATH` | writable cache Open-Meteo |
| `CDS_API_URL`, `CDS_API_KEY` | optional ERA5/CDS integration |
| `OPENROUTER_API_KEY` | optional LLM adapter |

Шаблон для ручного development-запуска: `.env.example`. Production-файл создаётся `scripts/deploy.sh` с правами `0640 root:cropbot`.

После изменения production-конфигурации:

```bash
sudo systemctl restart crop-forecast-bot
sudo bash /opt/crop-forecast-bot/current/scripts/status.sh
```

## Локальная разработка

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN и DATABASE_URL
python -m src.bot.main
```

## Тесты и CI

```bash
. .venv/bin/activate
ruff check config src tests
bash -n scripts/*.sh
shellcheck -x scripts/*.sh
python -m pytest -q
```

GitHub Actions выполняет Python static checks, `compileall`, unit tests и проверку всех нативных bash-скриптов. Также проверяется отсутствие контейнерных deployment-файлов.

## Научные ограничения текущего среза

- Open-Meteo предоставляет 14 суток прошлого периода и 7 суток прогноза для оперативного отчёта.
- ГДД без даты посева показываются только за доступный период; фенофаза не выводится.
- ГТК не рассчитывается при недостаточном числе тёплых суток.
- ET₀ обозначается как provider variable Open-Meteo.
- температурный риск — screening по Tmin воздуха на высоте 2 м; он не учитывает температуру поверхности, микрорельеф и фактическую фазу культуры.
- SPI по короткому прогнозу не рассчитывается.

## Документация

- [Быстрый старт и эксплуатация](QUICK_START_GUIDE.md)
- [Аудит 2026-07-10](docs/AUDIT_2026-07-10.md)
- [План модернизации](docs/DEVELOPMENT_PLAN.md)
- [RAG guide](RAG_GUIDE.md)

## Ближайшие обязательные работы

1. Alembic baseline и отказ от `create_all()` в production.
2. Redis deduplication/lock для scheduler.
3. Дата посева, сезон и фенофаза в профиле поля.
4. Интеграционные тесты PostgreSQL/Redis/API и FSM restart.
5. Provider interfaces для ERA5, SoilGrids и спутниковых данных.
6. Зафиксированный lock-файл после проверки на Debian 12 и Astra Linux.
7. Clean-host smoke test нативной установки и проверка rollback после отказа.

Подробные критерии готовности зафиксированы в `docs/DEVELOPMENT_PLAN.md`.
