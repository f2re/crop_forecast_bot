from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.late_blight_monitoring import (
    acknowledge_manual_late_blight_view,
)
from src.database.biological_monitoring import (
    enable_late_blight_monitor,
    get_active_late_blight_context,
)
from src.database.crud import save_coordinates, update_user_crop
from src.database.models import Base
from src.domain.late_blight import (
    LateBlightOutlook,
    LateBlightPeriod,
)


@pytest.mark.asyncio
async def test_manual_view_advances_enabled_monitor_baseline(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'late-blight-manual.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with sessions() as session:
            await save_coordinates(session, 8201, 55.75, 37.62)
            await update_user_crop(session, 8201, "potato")
            context = await enable_late_blight_monitor(session, 8201)
            period = LateBlightPeriod(
                start_date=date(2026, 8, 5),
                end_date=date(2026, 8, 8),
                day_count=4,
                data_kind="forecast",
            )
            outlook = LateBlightOutlook(
                available=True,
                status="критерии Hutton выполнены",
                criteria_name="Hutton Criteria",
                days=(),
                periods=(period,),
                timezone="UTC",
                source="test",
                model="test",
                retrieved_at=datetime(2026, 8, 3, 12, tzinfo=timezone.utc),
            )
            decision = await acknowledge_manual_late_blight_view(
                session,
                context,
                outlook,
                now_utc=datetime(2026, 8, 3, 12, tzinfo=timezone.utc),
            )
            assert decision is not None
            assert decision.change is not None

            saved = await get_active_late_blight_context(session, 8201)
            assert saved is not None
            assert saved.delivery_state.active_periods
            assert saved.last_notified_at is not None
    finally:
        await engine.dispose()
