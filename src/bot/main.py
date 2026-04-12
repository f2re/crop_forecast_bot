"""
Основной вход для Telegram-бота на aiogram 3.x.
Инициализация RAG, планировщика и регистрация роутеров.
"""
import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Dict

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from config.settings import TELEGRAM_BOT_TOKEN, get_database_url
from src.database import init_db
from src.knowledge.rag_engine import get_rag_engine
from src.bot.scheduler import start_scheduler

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """Middleware для инъекции сессии БД в хэндлеры."""
    def __init__(self, session_factory):
        super().__init__()
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            return await handler(event, data)


async def on_startup(bot: Bot):
    """Хук при запуске."""
    logger.info("🚀 Запуск агробота...")
    
    # 1. Проверка RAG
    rag = get_rag_engine()
    if rag.is_available():
        logger.info("✅ RAG база знаний доступна")
    else:
        logger.warning("⚠️ RAG база пуста. Проиндексируйте документы.")
    
    # 2. Запуск планировщика
    await start_scheduler(bot)


async def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("BOT_TOKEN не найден в .env")
        return

    # Инициализация БД
    db_url = get_database_url()
    db = init_db(db_url)
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация Middleware
    dp.update.middleware(DbSessionMiddleware(db.get_session))

    # Регистрация роутеров
    from src.bot.handlers.rag import router as rag_router
    # Примечание: agro_router и main_router должны быть созданы 
    # путём миграции существующих telebot хэндлеров.
    dp.include_router(rag_router)

    dp.startup.register(on_startup)

    logger.info("Бот готов к работе (aiogram 3.x)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
