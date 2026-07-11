from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
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
from src.bot.middlewares import CallbackIdempotencyMiddleware
from src.bot.scheduler import start_scheduler, stop_scheduler
from src.database import Database, init_db
from src.database.schema import require_current_schema
from src.infrastructure.coordination import create_coordination
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
            BotCommand(command="help", description="Показать справку"),
            BotCommand(command="cancel", description="Отменить текущий ввод"),
        ]
    )


async def run() -> None:
    settings = get_settings()
    settings.validate()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    async with AsyncExitStack() as stack:
        stack.push_async_callback(close_open_meteo_resources)
        database: Database = init_db(settings.database_url)
        stack.push_async_callback(database.dispose)
        await database.ping()
        await require_current_schema(database.engine)

        bot = Bot(
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

        dispatcher = Dispatcher(storage=storage)
        dispatcher.update.middleware(DbSessionMiddleware(database.get_session))
        dispatcher.callback_query.outer_middleware(
            CallbackIdempotencyMiddleware(coordination)
        )

        from src.bot.handlers.core import router as core_router
        from src.bot.handlers.rag import router as rag_router
        from src.bot.handlers.settings import router as settings_router

        # Settings precede the legacy core handlers so old toggle callbacks are
        # rejected rather than replayed as non-idempotent state inversions.
        dispatcher.include_router(settings_router)
        dispatcher.include_router(core_router)
        dispatcher.include_router(rag_router)
        await configure_bot_commands(bot)

        heartbeat_task = asyncio.create_task(
            run_heartbeat(settings.heartbeat_file),
            name="runtime-heartbeat",
        )
        try:
            await start_scheduler(bot, database.get_session, coordination)
            logger.info("Crop Forecast Bot started with aiogram")
            notify_ready()
            await dispatcher.start_polling(
                bot,
                allowed_updates=dispatcher.resolve_used_update_types(),
                close_bot_session=False,
            )
        finally:
            notify_stopping()
            await stop_scheduler()
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            logger.info("Crop Forecast Bot stopped cleanly")


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
