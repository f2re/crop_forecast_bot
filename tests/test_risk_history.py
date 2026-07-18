from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.risk_history import build_risk_history
from src.bot.risk_history import format_risk_history
from src.database.models import (
    Base,
    Field,
    RiskForecastRun,
    RiskForecastSignal,
    User,
)
from src.database.risk_history import (
    list_recent_risk_runs,
    prune_risk_runs_before,
    save_risk_run,
    set_signal_delivery,
)
from src.domain.risk import EnsembleForecastMeta, RiskEvent, RiskOutlook
from src.domain.risk_trend import classify_risk_trend


def _meta(retrieved_at: datetime) -> EnsembleForecastMeta:
    return EnsembleForecastMeta(
        latitude=55.75,
        longitude=37.62,
        elevation_m=150.0,
        timezone="Europe/Moscow",
        source="test ensemble",
        model="gfs_seamless",
        retrieved_at=retrieved_at,
        member_count=31,
        forecast_days=16,
    )


def _event(
    *,
    risk_type: str = "heavy_rain",
    event_date: date = date(2026, 7, 22),
    fraction: float = 0.4,
    level: str = "elevated",
) -> RiskEvent:
    members = round(fraction * 30)
    return RiskEvent(
        risk_type=risk_type,  # type: ignore[arg-type]
        event_date=event_date,
        lead_days=4,
        level=level,  # type: ignore[arg-type]
        members_exceeding=members,
        valid_members=30,
        member_fraction=fraction,
        severe_members_exceeding=0,
        severe_member_fraction=0.0,
        threshold=30.0,
        severe_threshold=50.0,
        unit="мм/сут",
        p10=1.0,
        median=20.0,
        p90=55.0,
        model="gfs_seamless",
        reliability_note="средний срок",
        action="Проверьте водоотвод.",
        caveat="Скрининг модельной ячейки.",
    )


def _outlook(*events: RiskEvent, analysis_date: date = date(2026, 7, 18)) -> RiskOutlook:
    return RiskOutlook(
        available=True,
        status=(
            "риски выше порога уведомления выявлены"
            if events
            else "в полном валидном ансамбле риски не выявлены"
        ),
        events=events,
        model="gfs_seamless",
        member_count=31,
        forecast_days=16,
        valid_days=16,
        incomplete_days=0,
        generated_for_date=analysis_date,
    )


async def _field_id(sessions) -> int:
    async with sessions() as session:
        user = User(telegram_id=1001, selected_crop="wheat")
        session.add(user)
        await session.flush()
        field = Field(
            user_id=user.id,
            name="Северное",
            latitude=55.75,
            longitude=37.62,
            timezone="Europe/Moscow",
            is_active=True,
        )
        session.add(field)
        await session.commit()
        return field.id


def test_signal_trend_uses_level_then_ten_point_fraction_delta() -> None:
    assert (
        classify_risk_trend(
            current_fraction=0.30,
            current_level="elevated",
            previous_fraction=None,
            previous_level=None,
        )
        == "new"
    )
    assert (
        classify_risk_trend(
            current_fraction=0.41,
            current_level="elevated",
            previous_fraction=0.30,
            previous_level="elevated",
        )
        == "strengthening"
    )
    assert (
        classify_risk_trend(
            current_fraction=0.35,
            current_level="elevated",
            previous_fraction=0.30,
            previous_level="elevated",
        )
        == "stable"
    )
    assert (
        classify_risk_trend(
            current_fraction=0.55,
            current_level="watch",
            previous_fraction=0.35,
            previous_level="elevated",
        )
        == "weakening"
    )


@pytest.mark.asyncio
async def test_run_and_signals_are_idempotent_and_delivery_is_recorded(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'history.sqlite'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    field_id = await _field_id(sessions)
    retrieved_at = datetime(2026, 7, 18, 6, 0, tzinfo=timezone.utc)

    try:
        async with sessions() as session:
            first = await save_risk_run(
                session,
                field_id=field_id,
                meta=_meta(retrieved_at),
                outlook=_outlook(_event()),
            )
        async with sessions() as session:
            second = await save_risk_run(
                session,
                field_id=field_id,
                meta=_meta(retrieved_at),
                outlook=_outlook(_event()),
            )

        assert first.created is True
        assert second.created is False
        assert first.run_id == second.run_id
        signal_id = next(iter(first.signal_ids.values()))

        async with sessions() as session:
            assert await set_signal_delivery(
                session,
                signal_id=signal_id,
                state="sent",
                notified_at=datetime(2026, 7, 18, 6, 5, tzinfo=timezone.utc),
            )
        async with sessions() as session:
            run_count = await session.scalar(select(func.count(RiskForecastRun.id)))
            signal_count = await session.scalar(
                select(func.count(RiskForecastSignal.id))
            )
            runs = await list_recent_risk_runs(session, field_id=field_id)

        assert run_count == 1
        assert signal_count == 1
        assert runs[0].signals[0].delivery_state == "sent"
        assert runs[0].signals[0].notified_at is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_history_marks_strengthening_and_cleared_signals(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'trend.sqlite'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    field_id = await _field_id(sessions)

    first_time = datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)
    second_time = datetime(2026, 7, 18, 6, 0, tzinfo=timezone.utc)
    old_wind = _event(
        risk_type="strong_wind",
        event_date=date(2026, 7, 23),
        fraction=0.35,
        level="elevated",
    )
    try:
        async with sessions() as session:
            await save_risk_run(
                session,
                field_id=field_id,
                meta=_meta(first_time),
                outlook=_outlook(
                    _event(fraction=0.30, level="elevated"),
                    old_wind,
                ),
            )
        async with sessions() as session:
            await save_risk_run(
                session,
                field_id=field_id,
                meta=_meta(second_time),
                outlook=_outlook(_event(fraction=0.50, level="elevated")),
            )
        async with sessions() as session:
            runs = await list_recent_risk_runs(session, field_id=field_id)

        history = build_risk_history(runs)
        trends = {(item.signal.risk_type, item.trend) for item in history.items}
        text = format_risk_history(
            history,
            field_name="Северное",
            crop="wheat",
        )

        assert ("heavy_rain", "strengthening") in trends
        assert ("strong_wind", "cleared") in trends
        assert "усиливается" in text
        assert "снят" in text
        assert "не является вероятностью" in text
        assert len(text) <= 4096
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_retention_removes_only_expired_runs(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retention.sqlite'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    field_id = await _field_id(sessions)
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new_time = datetime(2026, 7, 18, tzinfo=timezone.utc)

    try:
        async with sessions() as session:
            await save_risk_run(
                session,
                field_id=field_id,
                meta=_meta(old_time),
                outlook=_outlook(_event()),
            )
        async with sessions() as session:
            await save_risk_run(
                session,
                field_id=field_id,
                meta=_meta(new_time),
                outlook=_outlook(),
            )
        async with sessions() as session:
            deleted = await prune_risk_runs_before(
                session,
                cutoff=new_time - timedelta(days=90),
            )
        async with sessions() as session:
            runs = await list_recent_risk_runs(session, field_id=field_id, limit=10)

        assert deleted == 1
        assert len(runs) == 1
        assert runs[0].retrieved_at == new_time.replace(tzinfo=None)
    finally:
        await engine.dispose()
