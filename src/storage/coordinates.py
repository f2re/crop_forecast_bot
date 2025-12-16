"""
Coordinates storage module.
Provides synchronous wrapper for async database operations.
"""
import asyncio
from typing import Optional, Dict
import logging

from src.database import get_db
from src.database.crud import save_coordinates as db_save_coordinates
from src.database.crud import load_coordinates as db_load_coordinates

logger = logging.getLogger(__name__)


def save_coordinates(user_id: int, latitude: float, longitude: float, username: Optional[str] = None, first_name: Optional[str] = None):
    """
    Сохраняет координаты пользователя в базу данных.

    Args:
        user_id: Telegram user ID
        latitude: Широта
        longitude: Долгота
        username: Telegram username (optional)
        first_name: Имя пользователя (optional)
    """
    try:
        db = get_db()
        if not db:
            logger.error("Database not initialized")
            return

        async def _save():
            async with db.get_session() as session:
                await db_save_coordinates(
                    session=session,
                    telegram_id=user_id,
                    latitude=latitude,
                    longitude=longitude,
                    username=username,
                    first_name=first_name
                )

        # Run async operation in sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If event loop is already running, create a new task
            asyncio.create_task(_save())
        else:
            # Otherwise run synchronously
            asyncio.run(_save())

        logger.info(f"Координаты пользователя {user_id} сохранены: {latitude}, {longitude}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении координат: {e}", exc_info=True)
        raise


def load_coordinates(user_id: int) -> Optional[Dict[str, float]]:
    """
    Загружает координаты пользователя из базы данных.

    Args:
        user_id: Telegram user ID

    Returns:
        Dict с ключами 'latitude' и 'longitude' или None
    """
    try:
        db = get_db()
        if not db:
            logger.error("Database not initialized")
            return None

        async def _load():
            async with db.get_session() as session:
                coords = await db_load_coordinates(session=session, telegram_id=user_id)
                if coords:
                    return {
                        "latitude": coords[0],
                        "longitude": coords[1]
                    }
                return None

        # Run async operation in sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a new event loop for this sync call
            new_loop = asyncio.new_event_loop()
            try:
                result = new_loop.run_until_complete(_load())
                return result
            finally:
                new_loop.close()
        else:
            return asyncio.run(_load())
    except Exception as e:
        logger.error(f"Ошибка при загрузке координат: {e}", exc_info=True)
        return None
