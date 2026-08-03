from __future__ import annotations

import argparse
import asyncio
import copy
import logging
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack, suppress
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, TelegramObject

from config.settings import Settings, get_settings
from src.api.open_meteo import close_open_meteo_resources
from src.api.open_meteo_ensemble import close_open_meteo_ensemble_resources
from src.bot.errors import handle_runtime_error
from src.bot.middlewares import CallbackIdempotencyMiddleware
from src.bot.scheduler import (
    check_weather_risk_alerts,
    start_scheduler,
    stop_scheduler,
)
from src.bot.telegram_text import SafeHtmlBot
from src.database import Database, init_db
from src.database.schema import require_current_schema
from src.infrastructure.coordination import CoordinationBackend, create_coordination
from src.ops.heartbeat import notify_ready, notify_stopping, run_heartbeat

logger = logging.getLogger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_factory: Callable[[], Any]):
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            try:
                return await handler(event, data)
            except Exception:
                await session.rollback()
                raise


def build_storage(settings: Settings) -> BaseStorage:
    if settings.redis_url:
        logger.info("Persistent FSM storage: Redis")
        return RedisStorage.from_url(settings.redis_url)
    logger.warning("REDIS_URL is not set; FSM state will not survive restart")
    return MemoryStorage()


async def configure_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть главное меню"),
            BotCommand(command="crops", description="Культуры активного поля"),
            BotCommand(command="report", description="Агроотчёт выбранной культуры"),
            BotCommand(command="risks", description="Проверить погодные условия"),
            BotCommand(
                command="history",
                description="Показать историю предупреждений",
            ),
            BotCommand(command="help", description="Показать справку"),
            BotCommand(command="cancel", description="Отменить текущий ввод"),
        ]
    )


def build_dispatcher(
    *,
    storage: BaseStorage,
    session_factory: Callable[[], Any],
    coordination: CoordinationBackend,
    rag_enabled: bool = False,
) -> Dispatcher:
    """Build the production router graph without starting external services."""

    dispatcher = Dispatcher(storage=storage)
    dispatcher.errors.register(handle_runtime_error)
    dispatcher.update.middleware(DbSessionMiddleware(session_factory))
    dispatcher.callback_query.outer_middleware(
        CallbackIdempotencyMiddleware(coordination)
    )

    from src.bot.handlers.core import router as core_router
    from src.bot.handlers.crops import router as crops_router
    from src.bot.handlers.phenology import router as phenology_router
    from src.bot.handlers.profile import router as profile_router
    from src.bot.handlers.report import router as report_router
    from src.bot.handlers.report_help import router as report_help_router
    from src.bot.handlers.risk_history import router as risk_history_router
    from src.bot.handlers.risks import router as risks_router
    from src.bot.handlers.season_calendar import router as season_calendar_router
    from src.bot.handlers.settings import router as settings_router

    # Narrow feature routers precede the broad legacy core router. They own the
    # profile, crop, date, stage, report and contextual-help callbacks while the
    # remaining onboarding flow stays in core until it is split separately.
    dispatcher.include_router(copy.deepcopy(settings_router))
    dispatcher.include_router(copy.deepcopy(profile_router))
    dispatcher.include_router(copy.deepcopy(crops_router))
    dispatcher.include_router(copy.deepcopy(season_calendar_router))
    dispatcher.include_router(copy.deepcopy(phenology_router))
    dispatcher.include_router(copy.deepcopy(report_help_router))
    dispatcher.include_router(copy.deepcopy(report_router))
    dispatcher.include_router(copy.deepcopy(risks_router))
    dispatcher.include_router(copy.deepcopy(risk_history_router))
    dispatcher.include_router(copy.deepcopy(core_router))
    if rag_enabled:
        from src.bot.handlers.rag import router as rag_router

        dispatcher.include_router(copy.deepcopy(rag_router))
    return dispatcher


async def _run_startup_risk_check(
    bot: Bot,
    session_factory: Callable[[], Any],
    coordination: CoordinationBackend,
    delay_seconds: int,
) -> None:
    """Evaluate every saved alert-enabled field shortly after a healthy startup."""

    await asyncio.sleep(delay_seconds)
    try:
        await check_weather_risk_alerts(bot, session_factory, coordination)
    except asyncio.CancelledError:
        raise
    except Exception:
        # A provider outage must not terminate Telegram polling. The scheduler
        # will retry at the next configured cycle and records controlled errors.
        logger.exception("Startup weather-risk screening failed")


async def run(*, startup_smoke: bool = False) -> None:
    settings = get_settings()
    settings.validate()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # All synchronous provider adapters use asyncio.to_thread(). Bound the shared
    # executor so a weak server cannot create a large burst of worker threads.
    loop = asyncio.get_running_loop()
    blocking_executor = ThreadPoolExecutor(
        max_workers=settings.blocking_io_workers,
        thread_name_prefix="cropbot-io",
    )
    loop.set_default_executor(blocking_executor)

    async with AsyncExitStack() as stack:
        stack.callback(
            blocking_executor.shutdown,
            wait=True,
            cancel_futures=True,
        )
        stack.push_async_callback(close_open_meteo_resources)
        stack.push_async_callback(close_open_meteo_ensemble_resources)
        database: Database = init_db(settings.database_url)
        stack.push_async_callback(database.dispose)
        await database.ping()
        await require_current_schema(database.engine)

        bot = SafeHtmlBot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        stack.push_async_callback(bot.session.close)

        storage = build_storage(settings)
        stack.push_async_callback(storage.close)

        coordination = await create_coordination(
            settings.redis_url,
            namespace=settings.coordination_namespace,
        )
        stack.push_async_callback(coordination.close)
        logger.info(
            "Runtime coordination backend: %s",
            "Redis" if settings.redis_url else "process-local memory",
        )

        dispatcher = build_dispatcher(
            storage=storage,
            session_factory=database.get_session,
            coordination=coordination,
            rag_enabled=settings.rag_enabled,
        )

        if startup_smoke:
            try:
                await start_scheduler(bot, database.get_session, coordination)
                if not dispatcher.resolve_used_update_types():
                    raise RuntimeError("Dispatcher has no reachable update handlers")
                logger.info("MVP startup smoke passed")
                print("MVP startup smoke passed")
            finally:
                await stop_scheduler()
            return

        # Do not report systemd readiness until the real Telegram token and
        # network path have been accepted by Telegram. This prevents a release
        # with an invalid token or blocked egress from passing the health check.
        identity = await bot.get_me()
        logger.info(
            "Telegram API verified for bot id=%s username=%s",
            identity.id,
            identity.username or "<none>",
        )
        await configure_bot_commands(bot)

        heartbeat_task = asyncio.create_task(
            run_heartbeat(settings.heartbeat_file),
            name="runtime-heartbeat",
        )
        startup_risk_task: asyncio.Task[None] | None = None
        try:
            await start_scheduler(bot, database.get_session, coordination)
            if settings.risk_check_on_startup:
                startup_risk_task = asyncio.create_task(
                    _run_startup_risk_check(
                        bot,
                        database.get_session,
                        coordination,
                        settings.risk_check_startup_delay_seconds,
                    ),
                    name="startup-weather-risk-check",
                )
            logger.info("Crop Forecast Bot started with aiogram")
            notify_ready()
            await dispatcher.start_polling(
                bot,
                allowed_updates=dispatcher.resolve_used_update_types(),
                close_bot_session=False,
            )
        finally:
            notify_stopping()
            if startup_risk_task is not None:
                startup_risk_task.cancel()
                with suppress(asyncio.CancelledError):
                    await startup_risk_task
            await stop_scheduler()
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            logger.info("Crop Forecast Bot stopped cleanly")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Crop Forecast Telegram Bot")
    parser.add_argument(
        "--startup-smoke",
        action="store_true",
        help="assemble the production runtime without contacting Telegram",
    )
    args = parser.parse_args(argv)
    try:
        asyncio.run(run(startup_smoke=args.startup_smoke))
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
