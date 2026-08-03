from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.database.models import Base, Field, User
from src.database.risk_delivery_state import (
    load_risk_delivery_state,
    risk_delivery_states,
    save_risk_delivery_state,
)
from src.domain.risk_delivery import RiskEpisodeState


async def _field_id(sessions) -> int:
    async with sessions() as session:
        user = User(telegram_id=77001, selected_crop="wheat")
        session.add(user)
        await session.flush()
        field = Field(
            user_id=user.id,
            name="Южное",
            latitude=55.75,
            longitude=37.62,
            timezone="Europe/Moscow",
            is_active=True,
        )
        session.add(field)
        await session.commit()
        return field.id


@pytest.mark.asyncio
async def test_delivery_state_round_trip_including_empty_clear(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'risk-state.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    field_id = await _field_id(sessions)
    observed = datetime(2026, 8, 3, 6, tzinfo=timezone.utc)
    notified = datetime(2026, 8, 3, 6, 5, tzinfo=timezone.utc)
    episodes = (
        RiskEpisodeState(
            risk_type="heat",
            start_date=date(2026, 8, 5),
            end_date=date(2026, 8, 9),
            highest_level="elevated",
        ),
    )

    try:
        async with sessions() as session:
            await save_risk_delivery_state(
                session,
                field_id=field_id,
                model="gfs_seamless",
                delivery_mode="immediate",
                episodes=episodes,
                observed_at=observed,
                notified_at=notified,
            )
        async with sessions() as session:
            loaded = await load_risk_delivery_state(
                session,
                field_id=field_id,
                model="gfs_seamless",
                delivery_mode="immediate",
            )

        assert loaded is not None
        assert loaded.delivery_mode == "immediate"
        assert loaded.episodes == episodes
        assert loaded.last_observed_at == observed.replace(tzinfo=None)
        assert loaded.last_notified_at == notified.replace(tzinfo=None)

        async with sessions() as session:
            await save_risk_delivery_state(
                session,
                field_id=field_id,
                model="gfs_seamless",
                delivery_mode="immediate",
                episodes=(),
                observed_at=observed.replace(hour=12),
            )
        async with sessions() as session:
            cleared = await load_risk_delivery_state(
                session,
                field_id=field_id,
                model="gfs_seamless",
                delivery_mode="immediate",
            )

        assert cleared is not None
        assert cleared.episodes == ()
        assert cleared.last_notified_at == notified.replace(tzinfo=None)
        async with sessions() as session:
            model_mismatch = await load_risk_delivery_state(
                session,
                field_id=field_id,
                model="other_model",
                delivery_mode="immediate",
            )
            mode_mismatch = await load_risk_delivery_state(
                session,
                field_id=field_id,
                model="gfs_seamless",
                delivery_mode="digest",
            )
        assert model_mismatch is None
        assert mode_mismatch is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_corrupt_delivery_state_fails_closed(tmp_path) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'risk-state-corrupt.sqlite'}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    field_id = await _field_id(sessions)

    try:
        async with sessions() as session:
            await session.execute(
                insert(risk_delivery_states).values(
                    field_id=field_id,
                    model="gfs_seamless",
                    delivery_mode="immediate",
                    state_version=1,
                    state_json="[]",
                    last_observed_at=datetime(2026, 8, 3),
                )
            )
            await session.commit()
        async with sessions() as session:
            await session.execute(
                update(risk_delivery_states)
                .where(risk_delivery_states.c.field_id == field_id)
                .values(state_json='[{"risk_type":"heat"}]')
            )
            await session.commit()
        async with sessions() as session:
            with pytest.raises(RuntimeError, match="Invalid persisted"):
                await load_risk_delivery_state(
                    session,
                    field_id=field_id,
                    model="gfs_seamless",
                    delivery_mode="immediate",
                )
    finally:
        await engine.dispose()
