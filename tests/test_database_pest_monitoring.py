from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.crud import save_coordinates, update_user_crop
from src.database.models import Base
from src.database.pest_monitoring import (
    disable_pest_monitor,
    get_active_pest_context,
    list_enabled_pest_targets,
    mark_pest_monitor_checked,
    upsert_pest_monitor,
)


@pytest.mark.asyncio
async def test_potato_pest_monitor_is_persisted_and_disabled(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'pest-monitor.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 2001, 45.75, 33.875)
            await update_user_crop(session, 2001, "potato")
            saved = await upsert_pest_monitor(
                session,
                2001,
                pest_key="colorado_potato_beetle",
                biofix_date=date(2026, 6, 1),
            )
            assert saved.monitor_id is not None
            assert saved.enabled is True
            assert saved.biofix_date == date(2026, 6, 1)
            assert saved.biofix_type == "first_eggs"

        async with sessions() as session:
            targets = await list_enabled_pest_targets(session)
            assert len(targets) == 1
            target = targets[0]
            assert target.telegram_id == 2001
            assert target.crop_key == "potato"
            assert target.pest_key == "colorado_potato_beetle"

            notified = datetime(2026, 6, 5, 8, tzinfo=timezone.utc)
            assert await mark_pest_monitor_checked(
                session,
                target.monitor_id,
                local_date=date(2026, 6, 5),
                stage_event_key="stage-event",
                notified_at=notified,
            )

        async with sessions() as session:
            loaded = await get_active_pest_context(
                session,
                2001,
                "colorado_potato_beetle",
            )
            assert loaded is not None
            assert loaded.last_checked_local_date == date(2026, 6, 5)
            assert loaded.last_notified_stage == "stage-event"

            disabled = await disable_pest_monitor(
                session,
                2001,
                "colorado_potato_beetle",
            )
            assert disabled.enabled is False

        async with sessions() as session:
            assert await list_enabled_pest_targets(session) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_changed_biofix_resets_delivery_state(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'pest-reset.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 2002, 45.75, 33.875)
            await update_user_crop(session, 2002, "potato")
            saved = await upsert_pest_monitor(
                session,
                2002,
                pest_key="colorado_potato_beetle",
                biofix_date=date(2026, 6, 1),
            )
            assert saved.monitor_id is not None
            await mark_pest_monitor_checked(
                session,
                saved.monitor_id,
                local_date=date(2026, 6, 5),
                stage_event_key="old-stage",
                advance_event_key="old-advance",
            )
            changed = await upsert_pest_monitor(
                session,
                2002,
                pest_key="colorado_potato_beetle",
                biofix_date=date(2026, 6, 3),
            )
            assert changed.last_checked_local_date is None
            assert changed.last_notified_stage is None
            assert changed.last_notified_advance is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pest_model_is_not_transferred_to_another_crop(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'pest-crop-guard.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 2003, 45.75, 33.875)
            await update_user_crop(session, 2003, "tomato")
            with pytest.raises(ValueError, match="не применяется"):
                await upsert_pest_monitor(
                    session,
                    2003,
                    pest_key="colorado_potato_beetle",
                    biofix_date=date(2026, 6, 1),
                )
    finally:
        await engine.dispose()
