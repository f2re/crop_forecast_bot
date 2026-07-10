# Crop Forecast Bot

Telegram-бот для оперативной агрометеорологической оценки поля. Production runtime использует **aiogram 3.x**, PostgreSQL и Redis.

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

Production entrypoint:

```bash
python -m src.bot.main
```

Legacy `pyTelegramBotAPI` runtime удалён.

## Быстрый запуск через Docker Compose

Требуются Docker Engine и Docker Compose v2.

```bash
git clone https://github.com/f2re/crop_forecast_bot.git
cd crop_forecast_bot
cp .env.example .env
```

Заполните минимум:

```dotenv
TELEGRAM_BOT_TOKEN=...
DB_PASSWORD=сложный-уникальный-пароль
```

Развёртывание:

```bash
bash scripts/deploy.sh
```

Проверка:

```bash
docker compose ps
docker compose logs --tail=200 bot
```

Обновление из `main`:

```bash
bash scripts/update.sh main
```

Скрипт допускает только fast-forward update, сохраняет копию `.env`, пересобирает образ и показывает состояние контейнеров.

## Native systemd

Для Debian-подобной системы предусмотрен шаблон hardened unit и установщик:

```bash
sudo bash scripts/install-systemd.sh
```

При первом запуске установщик создаёт `/etc/crop-forecast-bot.env` и завершает работу. Заполните:

- `TELEGRAM_BOT_TOKEN`;
- async `DATABASE_URL`;
- `REDIS_URL`;

После настройки повторите установку. Диагностика runtime:

```bash
sudo -u cropbot /opt/crop_forecast_bot/.venv/bin/python -m src.ops.doctor --runtime
journalctl -u crop-forecast-bot -f
```

## Конфигурация

Основные переменные:

| Переменная | Назначение |
|---|---|
| `TELEGRAM_BOT_TOKEN` | обязательный токен Telegram |
| `DATABASE_URL` | SQLAlchemy async URL, обычно `postgresql+asyncpg://...` |
| `REDIS_URL` | persistent FSM/cache, обязательно для production |
| `SCHEDULER_TIMEZONE` | timezone фоновых задач |
| `HEARTBEAT_FILE` | файл heartbeat event loop |
| `CDS_API_URL`, `CDS_API_KEY` | optional ERA5/CDS integration |
| `OPENROUTER_API_KEY` | optional LLM adapter |

Полный шаблон: `.env.example`.

## Healthcheck

Контейнер не считается здоровым по DNS или успешному импорту. Фоновая coroutine обновляет heartbeat-файл; healthcheck отклоняет отсутствующий или устаревший heartbeat.

PostgreSQL и Redis имеют отдельные healthcheck. Бот стартует после их готовности.

## Тесты и CI

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

GitHub Actions выполняет:

- ruff для мигрированного runtime;
- `compileall`;
- unit tests;
- production Docker build.

## Научные ограничения текущего среза

- Open-Meteo предоставляет 14 суток прошлого периода и 7 суток прогноза для оперативного отчёта.
- ГДД без даты посева показываются только за доступный период; фенофаза не выводится.
- ГТК не рассчитывается при недостаточном числе тёплых суток.
- ET₀ обозначается как provider variable Open-Meteo.
- температурный риск — screening по Tmin воздуха на высоте 2 м; он не учитывает температуру поверхности, микрорельеф и фактическую фазу культуры.
- SPI по короткому прогнозу не рассчитывается.

## Документация

- [Аудит 2026-07-10](docs/AUDIT_2026-07-10.md)
- [План модернизации](docs/DEVELOPMENT_PLAN.md)
- [RAG guide](RAG_GUIDE.md)

## Ближайшие обязательные работы

1. Alembic baseline и отказ от `create_all()` в production.
2. Redis deduplication/lock для scheduler.
3. Дата посева, сезон и фенофаза в профиле поля.
4. Интеграционные тесты PostgreSQL/Redis/API и FSM restart.
5. Provider interfaces для ERA5, SoilGrids and satellite data.
6. Сгенерированный lock-файл после проверки на Debian 12/Astra Linux 1.7.

Подробные критерии готовности зафиксированы в `docs/DEVELOPMENT_PLAN.md`.
