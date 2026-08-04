from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.late_blight_monitoring import (
    enable_open_field_late_blight_monitor,
    require_open_field_late_blight_scope,
)
from src.database.biological_monitoring import list_enabled_late_blight_targets
from src.database.crud import save_coordinates, update_user_crop
from src.database.late_blight_scope import open_field_late_blight_season_ids
from src.database.models import Base
from src.database.phenology import get_active_crop_phenology, set_growth_context


@pytest.mark.asyncio
async def test_unknown_scope_must_be_confirmed_before_hutton_monitor(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'late-blight-scope.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 8101, 55.75, 37.62)
            await update_user_crop(session, 8101, "potato")

            with pytest.raises(ValueError, match="Открытый грунт"):
                await require_open_field_late_blight_scope(session, 8101)
            with pytest.raises(ValueError, match="Открытый грунт"):
                await enable_open_field_late_blight_monitor(session, 8101)

            await set_growth_context(
                session,
                8101,
                production_system="open_field",
            )
            enabled = await enable_open_field_late_blight_monitor(session, 8101)
            assert enabled.enabled is True
            assert enabled.crop_key == "potato"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_greenhouse_rejects_outdoor_hutton_weather(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'late-blight-greenhouse.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 8102, 55.75, 37.62)
            await update_user_crop(session, 8102, "potato")
            await set_growth_context(
                session,
                8102,
                production_system="greenhouse",
            )

            with pytest.raises(ValueError, match="защищённому грунту"):
                await require_open_field_late_blight_scope(session, 8102)
            with pytest.raises(ValueError, match="защищённому грунту"):
                await enable_open_field_late_blight_monitor(session, 8102)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scheduler_scope_returns_only_confirmed_open_field_seasons(
    tmp_path,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'late-blight-target-scope.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            for telegram_id, production_system in (
                (8201, "open_field"),
                (8202, "greenhouse"),
            ):
                await save_coordinates(
                    session,
                    telegram_id,
                    55.75 + (telegram_id - 8201),
                    37.62,
                )
                await update_user_crop(session, telegram_id, "potato")
                await set_growth_context(
                    session,
                    telegram_id,
                    production_system=production_system,
                )

            open_profile = await get_active_crop_phenology(session, 8201)
            greenhouse_profile = await get_active_crop_phenology(session, 8202)
            assert open_profile is not None
            assert greenhouse_profile is not None

            # Repository-level creation is deliberately permissive for upgrade
            # compatibility. Runtime application and scheduler apply the scope.
            await enable_open_field_late_blight_monitor(session, 8201)
            from src.database.biological_monitoring import enable_late_blight_monitor

            await enable_late_blight_monitor(session, 8202)
            targets = await list_enabled_late_blight_targets(session)
            assert len(targets) == 2

            allowed = await open_field_late_blight_season_ids(
                session,
                tuple(target.season_id for target in targets),
            )
            assert allowed == frozenset({open_profile.season_id})
            assert greenhouse_profile.season_id not in allowed
    finally:
        await engine.dispose()
