from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.crud import (
    get_field_context,
    list_notification_targets,
    save_coordinates,
    set_manual_phase,
    set_season_start,
    update_field_metadata,
    update_user_crop,
)
from src.database.models import Base


@pytest.mark.asyncio
async def test_active_field_and_season_roundtrip(tmp_path) -> None:
    database_path = tmp_path / "repository.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as session:
        await save_coordinates(
            session,
            telegram_id=1001,
            latitude=55.75,
            longitude=37.62,
            username="farmer",
        )
        await update_user_crop(session, 1001, "sunflower")
        await set_season_start(session, 1001, date(2026, 4, 15))
        await set_manual_phase(session, 1001, "Бутонизация")

        context = await get_field_context(session, 1001)
        assert context is not None
        assert context.field_name == "Основное поле"
        assert context.crop_key == "sunflower"
        assert context.season_start_date == date(2026, 4, 15)
        assert context.phenological_phase == "Бутонизация"
        assert context.phase_source == "user"

        await update_field_metadata(
            session,
            context.field_id,
            timezone="Europe/Moscow",
            elevation_m=156.0,
        )
        refreshed = await get_field_context(session, 1001)
        assert refreshed is not None
        assert refreshed.timezone == "Europe/Moscow"
        assert refreshed.elevation_m == 156.0

        targets = await list_notification_targets(session)
        assert len(targets) == 1
        assert targets[0].field_id == context.field_id
        assert targets[0].selected_crop == "sunflower"
        assert targets[0].season_start_date == date(2026, 4, 15)
        assert targets[0].phenological_phase == "Бутонизация"

    await engine.dispose()
