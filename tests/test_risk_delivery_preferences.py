from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.models import Base, Field, User
from src.database.risk_delivery_preferences import (
    get_risk_delivery_preferences,
    set_risk_delivery_mode,
    set_risk_quiet_hours,
)


@pytest.mark.asyncio
async def test_risk_delivery_preferences_are_field_scoped_and_persistent(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'risk-delivery.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            user = User(telegram_id=1001)
            session.add(user)
            await session.flush()
            field = Field(
                user_id=user.id,
                name="Северное",
                latitude=55.75,
                longitude=37.62,
                timezone="Europe/Moscow",
                is_active=True,
            )
            session.add(field)
            await session.commit()
            field_id = field.id

        async with sessions() as session:
            defaults = await get_risk_delivery_preferences(
                session,
                telegram_id=1001,
                field_id=field_id,
            )
        assert defaults.mode == "immediate"
        assert defaults.quiet_hours_start is None
        assert defaults.quiet_hours_end is None

        async with sessions() as session:
            changed = await set_risk_delivery_mode(
                session,
                telegram_id=1001,
                field_id=field_id,
                mode="digest",
            )
        assert changed.mode == "digest"

        async with sessions() as session:
            changed = await set_risk_quiet_hours(
                session,
                telegram_id=1001,
                field_id=field_id,
                start_hour=22,
                end_hour=7,
            )
        assert (changed.quiet_hours_start, changed.quiet_hours_end) == (22, 7)

        async with sessions() as session:
            stored = await get_risk_delivery_preferences(
                session,
                telegram_id=1001,
                field_id=field_id,
            )
        assert stored.mode == "digest"
        assert (stored.quiet_hours_start, stored.quiet_hours_end) == (22, 7)

        async with sessions() as session:
            cleared = await set_risk_quiet_hours(
                session,
                telegram_id=1001,
                field_id=field_id,
                start_hour=None,
                end_hour=None,
            )
        assert cleared.quiet_hours_start is None
        assert cleared.quiet_hours_end is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_risk_delivery_preferences_reject_other_users_field(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'risk-delivery-ownership.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            owner = User(telegram_id=1001)
            other = User(telegram_id=2002)
            session.add_all([owner, other])
            await session.flush()
            field = Field(
                user_id=owner.id,
                name="Северное",
                latitude=55.75,
                longitude=37.62,
                is_active=True,
            )
            session.add(field)
            await session.commit()
            field_id = field.id

        async with sessions() as session:
            with pytest.raises(ValueError, match="недоступно"):
                await set_risk_delivery_mode(
                    session,
                    telegram_id=2002,
                    field_id=field_id,
                    mode="high_only",
                )
    finally:
        await engine.dispose()
