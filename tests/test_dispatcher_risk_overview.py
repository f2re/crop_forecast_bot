from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import src.bot.handlers.risks as risks_module
from src.bot.main import build_dispatcher
from src.database.models import Base
from src.infrastructure.coordination import MemoryCoordination
from tests.bot_harness import RecordingSession, callback_update, make_bot, message_update


@pytest.mark.asyncio
async def test_dispatcher_manual_risk_overview_flow(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'risk-overview.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def fake_generate(latitude, longitude, *, as_of_date=None, provider=None):
        assert latitude == pytest.approx(55.7558)
        assert longitude == pytest.approx(37.6173)
        assert as_of_date is not None
        return SimpleNamespace(outlook=object(), meta=object())

    def fake_format(overview, *, field_name, crop, crops=(), phase=None):
        assert field_name == "Основное поле"
        assert crop == "sunflower"
        assert set(crops) == {"wheat", "sunflower"}
        assert phase is None
        return "⚠️ TEST MANUAL RISK OVERVIEW"

    monkeypatch.setattr(risks_module, "generate_risk_overview", fake_generate)
    monkeypatch.setattr(risks_module, "format_risk_overview", fake_format)

    storage = MemoryStorage()
    coordination = MemoryCoordination(namespace="risk-overview-flow")
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
            callback_update(5, data="risk_overview"),
        ]
        for update in updates:
            await dispatcher.feed_update(bot, update)

        assert any("вариантов прогноза" in text for text in telegram.texts)
        assert any("TEST MANUAL RISK OVERVIEW" in text for text in telegram.texts)
    finally:
        await storage.close()
        await coordination.close()
        await bot.session.close()
        await engine.dispose()
