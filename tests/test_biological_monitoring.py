from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.biological_monitoring import (
    LateBlightMonitoringTarget,
    collapse_late_blight_targets,
    disable_late_blight_monitor,
    enable_late_blight_monitor,
    get_active_late_blight_context,
    list_enabled_late_blight_targets,
    save_late_blight_delivery_state,
)
from src.database.crud import save_coordinates, update_user_crop
from src.database.models import Base
from src.domain.late_blight_delivery import (
    LateBlightDeliveryState,
    LateBlightEpisodeState,
    empty_late_blight_delivery_state,
)


@pytest.mark.asyncio
async def test_late_blight_monitor_enable_persist_disable_round_trip(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'late-blight-monitor.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 7001, 55.75, 37.62)
            await update_user_crop(session, 7001, "potato")
            initial = await get_active_late_blight_context(session, 7001)
            assert initial is not None
            assert initial.monitor_id is None
            assert initial.enabled is False

            enabled = await enable_late_blight_monitor(session, 7001)
            assert enabled.monitor_id is not None
            assert enabled.enabled is True
            assert enabled.delivery_state == empty_late_blight_delivery_state()

            state = LateBlightDeliveryState(
                active_periods=(
                    LateBlightEpisodeState(
                        date(2026, 8, 5),
                        date(2026, 8, 8),
                    ),
                ),
                withdrawn_periods=(),
                inoculum_context="unknown",
            )
            observed_at = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
            notified_at = datetime(2026, 8, 3, 12, 5, tzinfo=timezone.utc)
            await save_late_blight_delivery_state(
                session,
                monitor_ids=(enabled.monitor_id,),
                state=state,
                checked_local_date=date(2026, 8, 3),
                observed_at=observed_at,
                notified_at=notified_at,
            )

            restored = await get_active_late_blight_context(session, 7001)
            assert restored is not None
            assert restored.delivery_state == state
            assert restored.last_checked_local_date == date(2026, 8, 3)
            assert restored.last_notified_at is not None

            targets = await list_enabled_late_blight_targets(session)
            assert len(targets) == 1
            assert targets[0].crop_key == "potato"
            assert targets[0].delivery_state == state

            disabled = await disable_late_blight_monitor(session, 7001)
            assert disabled.enabled is False
            assert await list_enabled_late_blight_targets(session) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_non_potato_monitor_cannot_be_enabled(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'late-blight-crop.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 7002, 55.75, 37.62)
            await update_user_crop(session, 7002, "tomato")
            with pytest.raises(ValueError, match="только для картофеля"):
                await enable_late_blight_monitor(session, 7002)
    finally:
        await engine.dispose()


def _target(
    *,
    monitor_id: int,
    field_id: int,
    field_name: str,
    state: LateBlightDeliveryState,
    observed_at: datetime | None,
) -> LateBlightMonitoringTarget:
    return LateBlightMonitoringTarget(
        telegram_id=9001,
        monitor_id=monitor_id,
        monitor_ids=(monitor_id,),
        field_id=field_id,
        field_ids=(field_id,),
        field_name=field_name,
        field_names=(field_name,),
        latitude=55.75,
        longitude=37.62,
        timezone="Europe/Moscow",
        season_id=field_id * 10,
        crop_key="potato",
        inoculum_context="unknown",
        delivery_state=state,
        last_checked_local_date=None,
        last_observed_at=observed_at,
        last_notified_at=None,
        risk_delivery_mode="immediate",
        quiet_hours_start=None,
        quiet_hours_end=None,
    )


def test_duplicate_coordinate_monitors_are_collapsed_using_newest_state() -> None:
    old_state = empty_late_blight_delivery_state()
    new_state = LateBlightDeliveryState(
        active_periods=(
            LateBlightEpisodeState(date(2026, 8, 5), date(2026, 8, 8)),
        ),
        withdrawn_periods=(),
        inoculum_context="unknown",
    )
    collapsed = collapse_late_blight_targets(
        [
            _target(
                monitor_id=1,
                field_id=10,
                field_name="Картофель север",
                state=old_state,
                observed_at=datetime(2026, 8, 3, 6),
            ),
            _target(
                monitor_id=2,
                field_id=11,
                field_name="Картофель копия",
                state=new_state,
                observed_at=datetime(2026, 8, 3, 12),
            ),
        ]
    )

    assert len(collapsed) == 1
    target = collapsed[0]
    assert target.monitor_id == 1
    assert target.monitor_ids == (1, 2)
    assert target.field_ids == (10, 11)
    assert target.field_name == "Картофель север / Картофель копия"
    assert target.delivery_state == new_state
