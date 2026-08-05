from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.bot.late_blight_scheduler import check_late_blight_monitoring
from src.database.biological_monitoring import (
    enable_late_blight_monitor,
    get_active_late_blight_context,
)
from src.database.crud import save_coordinates, update_user_crop
from src.database.models import Base, Field
from src.database.phenology import set_growth_context
from src.domain.late_blight import LateBlightWeatherData, LateBlightWeatherMeta
from src.infrastructure.coordination import MemoryCoordination


class MutableLateBlightProvider:
    def __init__(self, start: date, qualifying_days: int) -> None:
        self.start = start
        self.qualifying_days = qualifying_days
        self.calls = 0

    async def fetch(self, latitude: float, longitude: float) -> LateBlightWeatherData:
        self.calls += 1
        rows: list[dict[str, object]] = []
        for offset in range(4):
            local_day = self.start + timedelta(days=offset)
            for hour in range(24):
                qualifies = offset < self.qualifying_days
                rows.append(
                    {
                        "date": datetime.combine(
                            local_day,
                            time(hour=hour),
                            tzinfo=timezone.utc,
                        ),
                        "temperature_2m": 12.0 if qualifies else 8.0,
                        "relative_humidity_2m": (
                            95.0 if qualifies and hour < 6 else 80.0
                        ),
                    }
                )
        return LateBlightWeatherData(
            meta=LateBlightWeatherMeta(
                latitude=latitude,
                longitude=longitude,
                elevation_m=100.0,
                timezone="UTC",
                source="test",
                model="test-model",
                retrieved_at=datetime.combine(
                    self.start,
                    time(hour=6),
                    tzinfo=timezone.utc,
                ),
                cache_ttl_seconds=3600,
            ),
            hourly=pd.DataFrame(rows),
        )


class RecordingBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> object:
        self.messages.append((chat_id, text))
        return object()


async def _prepare_monitor(sessions, telegram_id: int, *, mode: str) -> None:
    async with sessions() as session:
        await save_coordinates(session, telegram_id, 55.75, 37.62)
        await update_user_crop(session, telegram_id, "potato")
        await set_growth_context(
            session,
            telegram_id,
            production_system="open_field",
        )
        context = await enable_late_blight_monitor(session, telegram_id)
        assert context.monitor_id is not None
        await session.execute(
            update(Field)
            .where(Field.id == context.field_id)
            .values(risk_delivery_mode=mode)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_late_blight_scheduler_sends_only_material_extension_and_withdrawal(
    tmp_path,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'late-blight-scheduler.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    today = datetime.now(timezone.utc).date()
    provider = MutableLateBlightProvider(today, qualifying_days=2)
    bot = RecordingBot()
    coordination = MemoryCoordination(namespace="late-blight-scheduler-test")
    try:
        await _prepare_monitor(sessions, 8101, mode="immediate")
        now = datetime.combine(today, time(hour=9), tzinfo=timezone.utc)

        for _ in range(2):
            await check_late_blight_monitoring(
                bot,  # type: ignore[arg-type]
                sessions,
                coordination,
                provider=provider,
                now_utc=now,
                job_lock_ttl_seconds=60,
                renew_interval_seconds=5,
            )
        assert len(bot.messages) == 1
        assert "Погодное окно ожидается" in bot.messages[0][1]

        # One extra day is ordinary forecast noise and stays silent.
        provider.qualifying_days = 3
        await check_late_blight_monitoring(
            bot,  # type: ignore[arg-type]
            sessions,
            coordination,
            provider=provider,
            now_utc=now,
            job_lock_ttl_seconds=60,
            renew_interval_seconds=5,
        )
        assert len(bot.messages) == 1

        # Two extra days change the practical inspection window.
        provider.qualifying_days = 4
        await check_late_blight_monitoring(
            bot,  # type: ignore[arg-type]
            sessions,
            coordination,
            provider=provider,
            now_utc=now,
            job_lock_ttl_seconds=60,
            renew_interval_seconds=5,
        )
        assert len(bot.messages) == 2
        assert "Период может продлиться" in bot.messages[1][1]

        provider.qualifying_days = 0
        for _ in range(2):
            await check_late_blight_monitoring(
                bot,  # type: ignore[arg-type]
                sessions,
                coordination,
                provider=provider,
                now_utc=now,
                job_lock_ttl_seconds=60,
                renew_interval_seconds=5,
            )
        assert len(bot.messages) == 3
        assert "больше не подтверждается прогнозом" in bot.messages[2][1]

        async with sessions() as session:
            saved = await get_active_late_blight_context(session, 8101)
            assert saved is not None
            assert saved.delivery_state.active_periods == ()
            assert saved.delivery_state.withdrawn_periods
    finally:
        await coordination.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_digest_retains_material_same_day_change_and_sends_next_local_day(
    tmp_path,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'late-blight-digest.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    today = datetime.now(timezone.utc).date()
    provider = MutableLateBlightProvider(today, qualifying_days=2)
    bot = RecordingBot()
    coordination = MemoryCoordination(namespace="late-blight-digest-test")
    try:
        await _prepare_monitor(sessions, 8102, mode="digest")
        first_now = datetime.combine(today, time(hour=9), tzinfo=timezone.utc)
        await check_late_blight_monitoring(
            bot,  # type: ignore[arg-type]
            sessions,
            coordination,
            provider=provider,
            now_utc=first_now,
            job_lock_ttl_seconds=60,
            renew_interval_seconds=5,
        )
        assert len(bot.messages) == 1

        provider.qualifying_days = 4
        await check_late_blight_monitoring(
            bot,  # type: ignore[arg-type]
            sessions,
            coordination,
            provider=provider,
            now_utc=first_now,
            job_lock_ttl_seconds=60,
            renew_interval_seconds=5,
        )
        assert len(bot.messages) == 1

        next_day = datetime.combine(
            today + timedelta(days=1),
            time(hour=9),
            tzinfo=timezone.utc,
        )
        await check_late_blight_monitoring(
            bot,  # type: ignore[arg-type]
            sessions,
            coordination,
            provider=provider,
            now_utc=next_day,
            job_lock_ttl_seconds=60,
            renew_interval_seconds=5,
        )
        assert len(bot.messages) == 2
        assert "Период может продлиться" in bot.messages[1][1]
    finally:
        await coordination.close()
        await engine.dispose()
