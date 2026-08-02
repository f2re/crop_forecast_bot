from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.crops import (
    add_or_select_crop,
    list_field_crop_keys,
    list_field_crops,
    remove_field_crop,
    select_field_crop,
)
from src.database.crud import (
    get_field_context,
    save_coordinates,
    set_manual_phase,
    set_season_start,
)
from src.database.models import Base


@pytest.mark.asyncio
async def test_field_keeps_separate_dates_and_phases_for_multiple_crops(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'field-crops.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 1001, 45.74617, 33.85254)
            initial = await get_field_context(session, 1001)
            assert initial is not None
            assert initial.crop_key == "wheat"

            tomato = await add_or_select_crop(session, 1001, "tomato")
            await set_season_start(session, 1001, date(2026, 4, 15))
            await set_manual_phase(session, 1001, "Цветение")

            potato = await add_or_select_crop(session, 1001, "potato")
            await set_season_start(session, 1001, date(2026, 5, 3))
            await set_manual_phase(session, 1001, "Бутонизация")

            crops = await list_field_crops(session, 1001)
            assert {item.crop_key for item in crops} == {
                "wheat",
                "tomato",
                "potato",
            }
            assert sum(item.is_selected for item in crops) == 1
            assert next(item for item in crops if item.is_selected).crop_key == "potato"

            await select_field_crop(session, 1001, tomato.season_id)
            tomato_context = await get_field_context(session, 1001)
            assert tomato_context is not None
            assert tomato_context.crop_key == "tomato"
            assert tomato_context.season_start_date == date(2026, 4, 15)
            assert tomato_context.phenological_phase == "Цветение"

            await select_field_crop(session, 1001, potato.season_id)
            potato_context = await get_field_context(session, 1001)
            assert potato_context is not None
            assert potato_context.crop_key == "potato"
            assert potato_context.season_start_date == date(2026, 5, 3)
            assert potato_context.phenological_phase == "Бутонизация"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_adding_existing_crop_selects_it_without_duplicate(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'crop-dedup.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 1002, 55.75, 37.62)
            first = await add_or_select_crop(session, 1002, "tomato")
            second = await add_or_select_crop(session, 1002, "potato")
            selected_again = await add_or_select_crop(session, 1002, "tomato")

            assert selected_again.season_id == first.season_id
            profiles = await list_field_crops(session, 1002)
            assert [item.crop_key for item in profiles].count("tomato") == 1
            assert sum(item.is_selected for item in profiles) == 1
            assert next(item for item in profiles if item.is_selected).crop_key == "tomato"

            selected_after_remove = await remove_field_crop(
                session,
                1002,
                selected_again.season_id,
            )
            assert selected_after_remove.crop_key in {"wheat", "potato"}
            context = await get_field_context(session, 1002)
            assert context is not None
            keys = await list_field_crop_keys(session, context.field_id)
            assert "tomato" not in keys
            assert second.season_id in {
                item.season_id for item in await list_field_crops(session, 1002)
            }

            remaining = await list_field_crops(session, 1002)
            removable = next(item for item in remaining if not item.is_selected)
            await remove_field_crop(session, 1002, removable.season_id)
            only = await list_field_crops(session, 1002)
            assert len(only) == 1
            with pytest.raises(ValueError, match="единственную культуру"):
                await remove_field_crop(session, 1002, only[0].season_id)
    finally:
        await engine.dispose()
