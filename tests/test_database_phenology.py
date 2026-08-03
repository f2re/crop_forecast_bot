from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.crud import save_coordinates, update_user_crop
from src.database.models import Base
from src.database.phenology import (
    get_active_crop_phenology,
    set_growth_context,
    set_observed_phase,
    set_season_date_with_basis,
)


@pytest.mark.asyncio
async def test_explicit_date_meaning_and_stage_confirmation_are_persisted(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'phenology.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 1001, 45.75, 33.875)
            await update_user_crop(session, 1001, "tomato")
            profile = await set_season_date_with_basis(
                session,
                1001,
                date(2026, 5, 10),
                "transplanting",
            )
            assert profile.date_basis == "transplanting"
            assert profile.season_start_date == date(2026, 5, 10)
            assert profile.sowing_date is None

            profile = await set_growth_context(
                session,
                1001,
                production_system="open_field",
                plant_type="indeterminate",
            )
            assert profile.production_system == "open_field"
            assert profile.plant_type == "indeterminate"

            confirmed = datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc)
            profile = await set_observed_phase(
                session,
                1001,
                "Завязывание плодов",
                confirmed_at=confirmed,
            )
            assert profile.phenological_phase == "Завязывание плодов"
            assert profile.phase_source == "user"
            assert profile.phase_confirmed_at is not None

        async with sessions() as session:
            loaded = await get_active_crop_phenology(session, 1001)
            assert loaded is not None
            assert loaded.date_basis == "transplanting"
            assert loaded.production_system == "open_field"
            assert loaded.plant_type == "indeterminate"
            assert loaded.phenological_phase == "Завязывание плодов"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_changing_origin_date_requires_new_stage_observation(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'phenology-reset.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 1002, 55.75, 37.62)
            await update_user_crop(session, 1002, "tomato")
            await set_season_date_with_basis(
                session,
                1002,
                date(2026, 4, 1),
                "sowing",
            )
            await set_observed_phase(session, 1002, "Цветение")
            changed = await set_season_date_with_basis(
                session,
                1002,
                date(2026, 5, 15),
                "transplanting",
            )

            assert changed.phenological_phase is None
            assert changed.phase_confirmed_at is None
            assert changed.date_basis == "transplanting"
            assert changed.sowing_date is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stage_outside_crop_catalog_is_rejected(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'phenology-validation.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 1003, 45.75, 33.875)
            await update_user_crop(session, 1003, "tomato")
            with pytest.raises(ValueError, match="справочник"):
                await set_observed_phase(session, 1003, "Колошение")
    finally:
        await engine.dispose()
