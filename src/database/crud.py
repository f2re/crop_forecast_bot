from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        session.add(user)
    else:
        if username is not None:
            user.username = username
        if first_name is not None:
            user.first_name = first_name
        user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def save_coordinates(
    session: AsyncSession,
    telegram_id: int,
    latitude: float,
    longitude: float,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    user = await get_or_create_user(session, telegram_id, username, first_name)
    user.latitude = latitude
    user.longitude = longitude
    user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def load_coordinates(
    session: AsyncSession,
    telegram_id: int,
) -> tuple[float, float] | None:
    user = await get_user(session, telegram_id)
    if user is None or user.latitude is None or user.longitude is None:
        return None
    return user.latitude, user.longitude


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_user_crop(session: AsyncSession, telegram_id: int) -> str:
    user = await get_user(session, telegram_id)
    return user.selected_crop if user and user.selected_crop else "wheat"


async def update_user_crop(
    session: AsyncSession,
    telegram_id: int,
    crop_key: str,
) -> User:
    user = await get_or_create_user(session, telegram_id)
    user.selected_crop = crop_key
    user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def set_daily_digest(
    session: AsyncSession,
    telegram_id: int,
    enabled: bool,
) -> User:
    user = await get_or_create_user(session, telegram_id)
    user.daily_digest = 1 if enabled else 0
    user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def get_all_active_users(session: AsyncSession) -> AsyncIterator[User]:
    result = await session.stream(
        select(User).where(User.latitude.is_not(None), User.longitude.is_not(None))
    )
    async for user in result.scalars():
        yield user


async def get_users_with_daily_digest(session: AsyncSession) -> AsyncIterator[User]:
    result = await session.stream(
        select(User).where(
            User.daily_digest == 1,
            User.latitude.is_not(None),
            User.longitude.is_not(None),
        )
    )
    async for user in result.scalars():
        yield user
