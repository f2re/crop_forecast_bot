from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import TelegramObject

from config.settings import Settings, get_settings
from src.bot.scheduler import start_scheduler, stop_scheduler
from src.database import Database, init_db
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


async def run() -> None:
    settings = get_settings()
    settings.validate()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    database: Database = init_db(settings.database_url)
    await database.ping()
    await database.create_tables()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = build_storage(settings)
    dispatcher = Dispatcher(storage=storage)
    dispatcher.update.middleware(DbSessionMiddleware(database.get_session))

    from src.bot.handlers.core import router as core_router
    from src.bot.handlers.rag import router as rag_router

    dispatcher.include_router(core_router)
    dispatcher.include_router(rag_router)

    heartbeat_task = asyncio.create_task(
        run_heartbeat(settings.heartbeat_file),
        name="runtime-heartbeat",
    )
    try:
        await start_scheduler(bot, database.get_session)
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
        await storage.close()
        await bot.session.close()
        await database.dispose()
        logger.info("Crop Forecast Bot stopped cleanly")


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
