from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.bot.pest_scheduler import check_pest_monitoring, pest_monitoring_is_due
from src.database.crud import save_coordinates, update_user_crop
from src.database.models import Base
from src.database.pest_monitoring import (
    get_active_pest_context,
    upsert_pest_monitor,
)
from src.domain.weather import AgroWeatherData, WeatherCoverage, WeatherMeta
from src.infrastructure.coordination import MemoryCoordination


class _Provider:
    async def fetch(self, latitude, longitude, *, season_start=None):
        assert season_start == date(2026, 6, 1)
        rows = []
        for offset in range(7):
            day = date(2026, 6, 1) + timedelta(days=offset)
            rows.append(
                {
                    "date": pd.Timestamp(day, tz="UTC"),
                    "local_date": day.isoformat(),
                    "t_min": 11.1,
                    "t_max": 51.1,
                    "data_kind": (
                        "operational_past" if day < date(2026, 6, 5) else "forecast"
                    ),
                    "data_source": "test",
                }
            )
        return AgroWeatherData(
            meta=WeatherMeta(
                latitude=latitude,
                longitude=longitude,
                elevation_m=25.0,
                utc_offset_seconds=3 * 3600,
                timezone="Europe/Simferopol",
                source="test weather",
                retrieved_at=datetime(2026, 6, 5, 6, tzinfo=timezone.utc),
            ),
            daily=pd.DataFrame(rows),
            hourly=pd.DataFrame(),
            past_days=4,
            forecast_days=3,
            coverage=WeatherCoverage(
                requested_season_start=season_start,
                actual_start=date(2026, 6, 1),
                actual_end=date(2026, 6, 7),
                season_coverage_complete=True,
            ),
        )


class _Bot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str):
        self.messages.append((chat_id, text))
        return object()


def test_pest_monitoring_due_uses_local_morning_and_date() -> None:
    now = datetime(2026, 6, 5, 5, 30, tzinfo=timezone.utc)
    assert pest_monitoring_is_due("Europe/Simferopol", None, now_utc=now)
    assert not pest_monitoring_is_due(
        "Europe/Simferopol",
        date(2026, 6, 5),
        now_utc=now,
    )
    assert not pest_monitoring_is_due(
        "America/New_York",
        None,
        now_utc=now,
    )


@pytest.mark.asyncio
async def test_pest_cycle_sends_once_and_marks_local_day(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'pest-scheduler.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    coordination = MemoryCoordination(namespace="pest-scheduler-test")
    bot = _Bot()
    now = datetime(2026, 6, 5, 5, 30, tzinfo=timezone.utc)
    try:
        async with sessions() as session:
            await save_coordinates(session, 3001, 45.75, 33.875)
            await update_user_crop(session, 3001, "potato")
            await upsert_pest_monitor(
                session,
                3001,
                pest_key="colorado_potato_beetle",
                biofix_date=date(2026, 6, 1),
            )

        await check_pest_monitoring(
            bot,  # type: ignore[arg-type]
            sessions,
            coordination,
            due_only=True,
            provider=_Provider(),
            now_utc=now,
            job_lock_ttl_seconds=60,
            renew_interval_seconds=5,
        )

        assert len(bot.messages) == 1
        assert "Пора проверить поле" in bot.messages[0][1]
        assert "не команда на обработку" in bot.messages[0][1]

        async with sessions() as session:
            saved = await get_active_pest_context(
                session,
                3001,
                "colorado_potato_beetle",
            )
            assert saved is not None
            assert saved.last_checked_local_date == date(2026, 6, 5)
            assert saved.last_notified_stage is not None

        await check_pest_monitoring(
            bot,  # type: ignore[arg-type]
            sessions,
            coordination,
            due_only=True,
            provider=_Provider(),
            now_utc=now,
            job_lock_ttl_seconds=60,
            renew_interval_seconds=5,
        )
        assert len(bot.messages) == 1
    finally:
        await coordination.close()
        await engine.dispose()
