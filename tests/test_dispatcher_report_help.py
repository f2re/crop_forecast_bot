from datetime import date

import pytest
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.bot.main import build_dispatcher
from src.database.crops import add_or_select_crop
from src.database.crud import save_coordinates, set_season_start
from src.database.models import Base
from src.infrastructure.coordination import MemoryCoordination
from tests.bot_harness import RecordingSession, callback_update, make_bot


@pytest.mark.asyncio
async def test_report_help_opens_for_active_crop(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'report-help.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as session:
        await save_coordinates(session, 1001, 45.75, 33.875)
        await add_or_select_crop(session, 1001, "tomato")
        await set_season_start(session, 1001, date(2026, 4, 15))

    storage = MemoryStorage()
    coordination = MemoryCoordination(namespace="report-help-flow")
    dispatcher = build_dispatcher(
        storage=storage,
        session_factory=sessions,
        coordination=coordination,
    )
    telegram = RecordingSession()
    bot = make_bot(telegram)

    try:
        await dispatcher.feed_update(
            bot,
            callback_update(1, data="report_help:heat"),
        )

        assert any("Как считается накопленное тепло" in text for text in telegram.texts)
        assert any("базовая температура <b>10.0 °C</b>" in text for text in telegram.texts)
        assert any("12.0 °C·сут" in text for text in telegram.texts)
    finally:
        await storage.close()
        await coordination.close()
        await bot.session.close()
        await engine.dispose()
