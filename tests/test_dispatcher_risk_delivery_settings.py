from __future__ import annotations

import pytest
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.bot.main import build_dispatcher
from src.database.models import Base, Field, User
from src.infrastructure.coordination import MemoryCoordination
from tests.bot_harness import RecordingSession, callback_update, make_bot


@pytest.mark.asyncio
async def test_dispatcher_updates_risk_delivery_mode_and_quiet_hours(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'risk-delivery-settings.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as session:
        user = User(telegram_id=1001, selected_crop="wheat")
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

    storage = MemoryStorage()
    coordination = MemoryCoordination(namespace="risk-delivery-settings")
    dispatcher = build_dispatcher(
        storage=storage,
        session_factory=sessions,
        coordination=coordination,
    )
    telegram = RecordingSession()
    bot = make_bot(telegram)

    try:
        updates = [
            callback_update(1, data="settings"),
            callback_update(2, data=f"risk_mode_menu:{field_id}"),
            callback_update(3, data=f"set_risk_mode:{field_id}:digest"),
            callback_update(4, data=f"quiet_hours_menu:{field_id}"),
            callback_update(5, data=f"set_quiet_hours:{field_id}:22-07"),
        ]
        for update in updates:
            await dispatcher.feed_update(bot, update)

        async with sessions() as session:
            stored = await session.scalar(select(Field).where(Field.id == field_id))
        assert stored is not None
        assert stored.risk_delivery_mode == "digest"
        assert stored.quiet_hours_start == 22
        assert stored.quiet_hours_end == 7
        assert any("один дайджест в сутки" in text for text in telegram.texts)
        assert any("22:00–07:00" in text for text in telegram.texts)
    finally:
        await storage.close()
        await coordination.close()
        await bot.session.close()
        await engine.dispose()
