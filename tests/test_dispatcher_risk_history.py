from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import src.bot.handlers.risk_history as history_module
from src.bot.main import build_dispatcher
from src.database.models import Base
from src.infrastructure.coordination import MemoryCoordination
from tests.bot_harness import RecordingSession, callback_update, make_bot, message_update


@pytest.mark.asyncio
async def test_dispatcher_risk_history_flow(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'risk-history-flow.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def fake_load(session, *, field_id):
        assert field_id > 0
        return SimpleNamespace(available=True)

    def fake_format(history, *, field_name, crop):
        assert history.available is True
        assert field_name == "Основное поле"
        assert crop == "sunflower"
        return "🕘 TEST RISK HISTORY"

    monkeypatch.setattr(history_module, "load_risk_history", fake_load)
    monkeypatch.setattr(history_module, "format_risk_history", fake_format)

    storage = MemoryStorage()
    coordination = MemoryCoordination(namespace="risk-history-flow")
    dispatcher = build_dispatcher(
        storage=storage,
        session_factory=sessions,
        coordination=coordination,
    )
    telegram = RecordingSession()
    bot = make_bot(telegram)

    try:
        updates = [
            message_update(1, text="/start"),
            callback_update(2, data="field_manual"),
            message_update(3, text="55.7558, 37.6173"),
            callback_update(4, data="crop_pick:sunflower"),
            callback_update(5, data="risk_history"),
        ]
        for update in updates:
            await dispatcher.feed_update(bot, update)

        assert any("TEST RISK HISTORY" in text for text in telegram.texts)
    finally:
        await storage.close()
        await coordination.close()
        await bot.session.close()
        await engine.dispose()
