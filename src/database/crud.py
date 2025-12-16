from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> User:
    """
    Get existing user or create new one.

    Args:
        session: Database session
        telegram_id: Telegram user ID
        username: Telegram username
        first_name: User's first name

    Returns:
        User object
    """
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        # Update username and first_name if changed
        needs_update = False

        if username and user.username != username:
            user.username = username
            needs_update = True

        if first_name and user.first_name != first_name:
            user.first_name = first_name
            needs_update = True

        if needs_update:
            await session.commit()
            await session.refresh(user)

    return user


async def save_coordinates(
    session: AsyncSession,
    telegram_id: int,
    latitude: float,
    longitude: float,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> User:
    """
    Save or update user coordinates.

    Args:
        session: Database session
        telegram_id: Telegram user ID
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        username: Optional Telegram username
        first_name: Optional user's first name

    Returns:
        Updated User object
    """
    # Get or create user
    user = await get_or_create_user(session, telegram_id, username, first_name)

    # Update coordinates
    user.latitude = latitude
    user.longitude = longitude
    user.updated_at = datetime.utcnow()

    await session.commit()
    await session.refresh(user)

    return user


async def load_coordinates(
    session: AsyncSession,
    telegram_id: int
) -> Optional[Tuple[float, float]]:
    """
    Load user coordinates.

    Args:
        session: Database session
        telegram_id: Telegram user ID

    Returns:
        Tuple of (latitude, longitude) or None if not found
    """
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user and user.latitude is not None and user.longitude is not None:
        return (user.latitude, user.longitude)

    return None


async def get_user(
    session: AsyncSession,
    telegram_id: int
) -> Optional[User]:
    """
    Get user by telegram_id.

    Args:
        session: Database session
        telegram_id: Telegram user ID

    Returns:
        User object or None if not found
    """
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()
