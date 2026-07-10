from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.crud import (
    activate_field,
    create_field,
    get_field_context,
    get_field_summary,
    list_fields,
    list_notification_targets,
    rename_field,
    save_coordinates,
    set_field_notifications,
    set_manual_phase,
    set_season_start,
    update_field_coordinates,
    update_field_metadata,
    update_user_crop,
)
from src.database.models import Base


async def _session_factory(tmp_path, name: str):
    database_path = tmp_path / name
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, sessions


@pytest.mark.asyncio
async def test_multi_field_contexts_and_notifications_are_isolated(tmp_path) -> None:
    engine, sessions = await _session_factory(tmp_path, "multi-field.sqlite")

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

        northern = await get_field_context(session, 1001)
        assert northern is not None
        await update_field_metadata(
            session,
            northern.field_id,
            timezone="Europe/Moscow",
            timezone_source="Open-Meteo Forecast API",
            elevation_m=156.0,
            elevation_source="Open-Meteo Forecast API",
        )
        northern = await set_field_notifications(
            session,
            1001,
            daily_digest=True,
            frost_alerts=False,
        )

        southern = await create_field(
            session,
            1001,
            name="Южное",
            latitude=45.04,
            longitude=38.98,
        )
        assert southern.is_active is True
        assert southern.crop_key == "sunflower"
        assert southern.daily_digest_enabled is True

        await update_user_crop(session, 1001, "corn")
        await set_season_start(session, 1001, date(2026, 5, 2))
        await set_manual_phase(session, 1001, "6 листьев")
        await update_field_metadata(
            session,
            southern.field_id,
            timezone="Europe/Moscow",
            timezone_source="Open-Meteo Forecast API",
            elevation_m=34.0,
            elevation_source="Open-Meteo Forecast API",
        )
        await set_field_notifications(
            session,
            1001,
            daily_digest=False,
            frost_alerts=True,
        )
        southern = await rename_field(
            session,
            1001,
            southern.field_id,
            "Южное поле",
        )

        fields = await list_fields(session, 1001)
        assert len(fields) == 2
        assert [field.is_active for field in fields].count(True) == 1
        assert fields[0].field_id == southern.field_id
        assert fields[0].crop_key == "corn"
        assert fields[0].season_start_date == date(2026, 5, 2)
        assert fields[0].phenological_phase == "6 листьев"
        assert fields[0].daily_digest_enabled is False
        assert fields[0].frost_alerts_enabled is True

        await update_field_coordinates(
            session,
            1001,
            northern.field_id,
            latitude=56.0,
            longitude=38.0,
        )
        still_active = await get_field_context(session, 1001)
        assert still_active is not None
        assert still_active.field_id == southern.field_id
        assert still_active.latitude == pytest.approx(45.04)

        northern_summary = await activate_field(session, 1001, northern.field_id)
        assert northern_summary.is_active is True
        assert northern_summary.latitude == pytest.approx(56.0)
        assert northern_summary.longitude == pytest.approx(38.0)
        assert northern_summary.timezone == "UTC"
        assert northern_summary.elevation_m is None
        assert northern_summary.crop_key == "sunflower"
        assert northern_summary.season_start_date == date(2026, 4, 15)
        assert northern_summary.phenological_phase == "Бутонизация"
        assert northern_summary.daily_digest_enabled is True
        assert northern_summary.frost_alerts_enabled is False

        restored = await get_field_context(session, 1001)
        assert restored is not None
        assert restored.field_id == northern.field_id
        assert restored.daily_digest is True
        assert restored.frost_alerts is False

        all_targets = await list_notification_targets(session)
        digest_targets = await list_notification_targets(
            session,
            daily_digest_only=True,
        )
        frost_targets = await list_notification_targets(
            session,
            frost_alerts_only=True,
        )
        assert [target.field_id for target in all_targets] == [northern.field_id]
        assert [target.field_id for target in digest_targets] == [northern.field_id]
        assert frost_targets == []

        await activate_field(session, 1001, southern.field_id)
        all_targets = await list_notification_targets(session)
        digest_targets = await list_notification_targets(
            session,
            daily_digest_only=True,
        )
        frost_targets = await list_notification_targets(
            session,
            frost_alerts_only=True,
        )
        assert [target.field_id for target in all_targets] == [southern.field_id]
        assert digest_targets == []
        assert [target.field_id for target in frost_targets] == [southern.field_id]

    await engine.dispose()


@pytest.mark.asyncio
async def test_field_name_uniqueness_and_ownership_are_enforced(tmp_path) -> None:
    engine, sessions = await _session_factory(tmp_path, "ownership.sqlite")

    async with sessions() as session:
        await save_coordinates(session, 1001, 55.75, 37.62)
        first = await get_field_context(session, 1001)
        assert first is not None
        await rename_field(session, 1001, first.field_id, "Северное")

        second = await create_field(
            session,
            1001,
            name="Южное",
            latitude=45.04,
            longitude=38.98,
        )
        with pytest.raises(ValueError, match="уже существует"):
            await rename_field(session, 1001, second.field_id, "северное")

        await save_coordinates(session, 2002, 59.93, 30.33)
        with pytest.raises(ValueError, match="недоступно"):
            await activate_field(session, 2002, first.field_id)
        with pytest.raises(ValueError, match="недоступно"):
            await get_field_summary(session, 2002, first.field_id)

    await engine.dispose()
