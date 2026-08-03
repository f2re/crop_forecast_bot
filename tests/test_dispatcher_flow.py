from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import src.bot.handlers.report as report_module
from src.bot.main import build_dispatcher
from src.database.crud import get_field_context
from src.database.models import Base
from src.database.phenology import get_active_crop_phenology
from src.infrastructure.coordination import MemoryCoordination
from tests.bot_harness import (
    RecordingSession,
    callback_update,
    make_bot,
    message_update,
)


@pytest.mark.asyncio
async def test_dispatcher_field_crop_season_phase_report_flow(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'dispatcher-flow.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def fake_report(*args, **kwargs):
        assert kwargs["season_start_date"].isoformat() == "2026-04-15"
        assert kwargs["phenological_phase"] == "Бутонизация"
        assert kwargs["field_name"] == "Основное поле"
        return SimpleNamespace(
            text="🌾 TEST AGRO REPORT",
            timezone="Europe/Moscow",
            metadata_source="test-weather-provider",
            elevation_m=156.0,
        )

    monkeypatch.setattr(report_module, "generate_agro_report", fake_report)

    storage = MemoryStorage()
    coordination = MemoryCoordination(namespace="dispatcher-flow")
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
            callback_update(5, data="season_start_set"),
            callback_update(6, data="season_calendar:manual"),
            message_update(7, text="15.04.2026"),
            callback_update(8, data="season_basis:sowing"),
            callback_update(9, data="season_phase"),
            callback_update(10, data="phase_pick:2"),
            callback_update(11, data="agro_report"),
        ]
        for update in updates:
            await dispatcher.feed_update(bot, update)

        async with sessions() as session:
            context = await get_field_context(session, 1001)
            phenology = await get_active_crop_phenology(session, 1001)

        assert context is not None
        assert phenology is not None
        assert context.field_name == "Основное поле"
        assert context.latitude == pytest.approx(55.7558)
        assert context.longitude == pytest.approx(37.6173)
        assert context.crop_key == "sunflower"
        assert context.season_start_date is not None
        assert context.season_start_date.isoformat() == "2026-04-15"
        assert context.phenological_phase == "Бутонизация"
        assert context.phase_source == "user"
        assert phenology.date_basis == "sowing"
        assert phenology.sowing_date is not None
        assert phenology.phase_confirmed_at is not None
        assert context.timezone == "Europe/Moscow"
        assert context.timezone_source == "test-weather-provider"
        assert context.elevation_m == pytest.approx(156.0)
        assert any("TEST AGRO REPORT" in text for text in telegram.texts)
    finally:
        await storage.close()
        await coordination.close()
        await bot.session.close()
        await engine.dispose()
