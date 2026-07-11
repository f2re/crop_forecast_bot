from __future__ import annotations

import asyncio
import os
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.database import Database
from src.database.crud import (
    activate_field,
    create_field,
    get_field_context,
    list_fields,
    list_notification_targets,
    save_coordinates,
    set_field_notifications,
    set_manual_phase,
    set_season_start,
    update_user_crop,
)
from src.database.schema import expected_schema_revision, require_current_schema

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _test_database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not value.startswith("postgresql+asyncpg://"):
        pytest.fail("TEST_DATABASE_URL must use postgresql+asyncpg")
    return value


async def _reset_database(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "DROP TABLE IF EXISTS "
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
async def test_postgres_adopts_legacy_schema_and_backfills_field_context() -> None:
    database_url = _test_database_url()
    await _reset_database(database_url)

    legacy_engine = create_async_engine(database_url)
    try:
        async with legacy_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    CREATE TABLE users (
                        id SERIAL PRIMARY KEY,
                        telegram_id BIGINT NOT NULL UNIQUE,
                        username VARCHAR(255),
                        first_name VARCHAR(255),
                        latitude DOUBLE PRECISION,
                        longitude DOUBLE PRECISION,
                        selected_crop VARCHAR(50) DEFAULT 'wheat',
                        daily_digest INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO users (
                        telegram_id,
                        username,
                        latitude,
                        longitude,
                        selected_crop,
                        daily_digest
                    ) VALUES (
                        1001,
                        'legacy_farmer',
                        55.75,
                        37.62,
                        'sunflower',
                        1
                    )
                    """
                )
            )
    finally:
        await legacy_engine.dispose()

    await asyncio.to_thread(_upgrade, database_url)

    database = Database(database_url)
    try:
        assert await require_current_schema(database.engine) == expected_schema_revision()
        async with database.get_session() as session:
            context = await get_field_context(session, 1001)
            assert context is not None
            assert context.field_name == "Основное поле"
            assert context.latitude == pytest.approx(55.75)
            assert context.longitude == pytest.approx(37.62)
            assert context.crop_key == "sunflower"
            assert context.daily_digest is True
            assert context.frost_alerts is True

        async with database.engine.connect() as connection:
            revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            assert revision == expected_schema_revision()
    finally:
        await database.dispose()
        await _reset_database(database_url)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_repository_serializes_concurrent_field_activation() -> None:
    database_url = _test_database_url()
    await _reset_database(database_url)
    await asyncio.to_thread(_upgrade, database_url)

    database = Database(database_url)
    try:
        async with database.get_session() as session:
            await save_coordinates(
                session,
                telegram_id=2002,
                latitude=55.75,
                longitude=37.62,
                username="farmer",
            )
            await update_user_crop(session, 2002, "sunflower")
            await set_season_start(session, 2002, date(2026, 4, 15))
            await set_manual_phase(session, 2002, "Бутонизация")
            north = await get_field_context(session, 2002)
            assert north is not None
            await set_field_notifications(
                session,
                2002,
                daily_digest=True,
                frost_alerts=False,
            )

            south = await create_field(
                session,
                2002,
                name="Южное",
                latitude=45.04,
                longitude=38.98,
            )
            await update_user_crop(session, 2002, "corn")
            await set_season_start(session, 2002, date(2026, 5, 2))
            await set_manual_phase(session, 2002, "6 листьев")
            await set_field_notifications(
                session,
                2002,
                daily_digest=False,
                frost_alerts=True,
            )

        async def activate(field_id: int) -> None:
            async with database.get_session() as session:
                await activate_field(session, 2002, field_id)

        await asyncio.gather(
            activate(north.field_id),
            activate(south.field_id),
        )

        async with database.get_session() as session:
            fields = await list_fields(session, 2002)
            active = [field for field in fields if field.is_active]
            assert len(active) == 1
            active_field = active[0]

            all_targets = await list_notification_targets(session)
            assert [target.field_id for target in all_targets] == [active_field.field_id]

            digest_targets = await list_notification_targets(
                session,
                daily_digest_only=True,
            )
            frost_targets = await list_notification_targets(
                session,
                frost_alerts_only=True,
            )
            if active_field.field_id == north.field_id:
                assert [target.field_id for target in digest_targets] == [north.field_id]
                assert frost_targets == []
            else:
                assert digest_targets == []
                assert [target.field_id for target in frost_targets] == [south.field_id]

        async with database.engine.connect() as connection:
            index_names = set(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexname
                            FROM pg_indexes
                            WHERE tablename IN ('fields', 'crop_seasons')
                            """
                        )
                    )
                ).scalars()
            )
            assert "uq_fields_one_active_per_user" in index_names
            assert "uq_crop_seasons_one_active_per_field" in index_names
    finally:
        await database.dispose()
        await _reset_database(database_url)
