from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.crud import (
    activate_field,
    create_field,
    get_field_context,
    save_coordinates,
    set_field_notifications,
    set_season_start,
    update_user_crop,
)
from src.database.models import Base
from src.database.notification_targets import list_enabled_notification_targets


@pytest.mark.asyncio
async def test_background_monitoring_includes_every_enabled_field(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'notification-targets.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 1001, 55.75, 37.62)
            await update_user_crop(session, 1001, "sunflower")
            await set_season_start(session, 1001, date(2026, 4, 15))
            north = await get_field_context(session, 1001)
            assert north is not None
            await set_field_notifications(
                session,
                1001,
                daily_digest=True,
                frost_alerts=False,
            )

            south = await create_field(
                session,
                1001,
                name="Южное",
                latitude=45.04,
                longitude=38.98,
            )
            await update_user_crop(session, 1001, "corn")
            await set_season_start(session, 1001, date(2026, 5, 2))
            await set_field_notifications(
                session,
                1001,
                daily_digest=False,
                frost_alerts=True,
            )

            all_targets = await list_enabled_notification_targets(session)
            digest_targets = await list_enabled_notification_targets(
                session,
                daily_digest_only=True,
            )
            frost_targets = await list_enabled_notification_targets(
                session,
                frost_alerts_only=True,
            )

            assert [target.field_id for target in all_targets] == [
                north.field_id,
                south.field_id,
            ]
            assert [target.field_id for target in digest_targets] == [north.field_id]
            assert [target.field_id for target in frost_targets] == [south.field_id]

            await activate_field(session, 1001, north.field_id)
            assert [
                target.field_id
                for target in await list_enabled_notification_targets(
                    session,
                    frost_alerts_only=True,
                )
            ] == [south.field_id]
    finally:
        await engine.dispose()
