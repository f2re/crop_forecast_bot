from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.database import Database
from src.database.crops import (
    add_or_select_crop,
    list_field_crops,
    remove_field_crop,
)
from src.database.crud import get_field_context, save_coordinates

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not value.startswith("postgresql+asyncpg://"):
        pytest.fail("TEST_DATABASE_URL must use postgresql+asyncpg")
    return value


async def _reset(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "DROP TABLE IF EXISTS "
                    "risk_forecast_signals, risk_forecast_runs, "
                    "crop_seasons, fields, users, alembic_version CASCADE"
                )
            )
    finally:
        await engine.dispose()


def _upgrade(database_url: str) -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_selected_crop_can_be_removed_without_partial_index_conflict() -> None:
    database_url = _database_url()
    await _reset(database_url)
    await asyncio.to_thread(_upgrade, database_url)

    database = Database(database_url)
    try:
        async with database.get_session() as session:
            await save_coordinates(session, 1700, 45.74617, 33.85254)
            tomato = await add_or_select_crop(session, 1700, "tomato")
            potato = await add_or_select_crop(session, 1700, "potato")
            await add_or_select_crop(session, 1700, "tomato")

            replacement = await remove_field_crop(session, 1700, tomato.season_id)
            profiles = await list_field_crops(session, 1700)
            context = await get_field_context(session, 1700)

            assert context is not None
            assert context.crop_key == replacement.crop_key
            assert replacement.crop_key in {"wheat", "potato"}
            assert sum(profile.is_selected for profile in profiles) == 1
            assert {profile.crop_key for profile in profiles} == {"wheat", "potato"}
            assert potato.season_id in {profile.season_id for profile in profiles}

        async with database.engine.connect() as connection:
            active_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM crop_seasons s "
                    "JOIN fields f ON f.id = s.field_id "
                    "JOIN users u ON u.id = f.user_id "
                    "WHERE u.telegram_id = 1700 AND s.is_active"
                )
            )
            tomato_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM crop_seasons s "
                    "JOIN fields f ON f.id = s.field_id "
                    "JOIN users u ON u.id = f.user_id "
                    "WHERE u.telegram_id = 1700 AND s.crop_key = 'tomato'"
                )
            )
        assert active_count == 1
        assert tomato_count == 0
    finally:
        await database.dispose()
        await _reset(database_url)
