from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import cast

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.risk import (
    EnsembleForecastMeta,
    RiskLevel,
    RiskOutlook,
    RiskType,
)

from .models import RiskForecastRun, RiskForecastSignal

DeliveryState = str
SignalKey = tuple[RiskType, date]
_ALLOWED_DELIVERY_STATES = {
    "not_attempted",
    "sending",
    "sent",
    "deduplicated",
    "deferred",
    "failed",
}


@dataclass(frozen=True, slots=True)
class StoredRiskRun:
    run_id: int
    signal_ids: dict[SignalKey, int]
    created: bool


@dataclass(frozen=True, slots=True)
class RiskSignalSnapshot:
    signal_id: int
    risk_type: RiskType
    event_date: date
    lead_days: int
    level: RiskLevel
    members_exceeding: int
    valid_members: int
    member_fraction: float
    severe_member_fraction: float
    threshold: float
    severe_threshold: float
    unit: str
    p10: float
    median: float
    p90: float
    delivery_state: DeliveryState
    notified_at: datetime | None


@dataclass(frozen=True, slots=True)
class RiskRunSnapshot:
    run_id: int
    field_id: int
    source: str
    model: str
    retrieved_at: datetime
    analysis_date: date
    timezone: str
    member_count: int
    forecast_days: int
    valid_days: int
    incomplete_days: int
    status: str
    signals: tuple[RiskSignalSnapshot, ...]


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


async def _find_run(
    session: AsyncSession,
    *,
    field_id: int,
    model: str,
    retrieved_at: datetime,
) -> RiskForecastRun | None:
    result = await session.execute(
        select(RiskForecastRun)
        .options(selectinload(RiskForecastRun.signals))
        .where(
            RiskForecastRun.field_id == field_id,
            RiskForecastRun.model == model,
            RiskForecastRun.retrieved_at == retrieved_at,
        )
    )
    return result.scalar_one_or_none()


def _stored(run: RiskForecastRun, *, created: bool) -> StoredRiskRun:
    signal_ids = {
        (cast(RiskType, signal.risk_type), signal.event_date): signal.id
        for signal in run.signals
    }
    return StoredRiskRun(run_id=run.id, signal_ids=signal_ids, created=created)


def _signal_model(event) -> RiskForecastSignal:
    return RiskForecastSignal(
        risk_type=event.risk_type,
        event_date=event.event_date,
        lead_days=event.lead_days,
        level=event.level,
        members_exceeding=event.members_exceeding,
        valid_members=event.valid_members,
        member_fraction=event.member_fraction,
        severe_member_fraction=event.severe_member_fraction,
        threshold=event.threshold,
        severe_threshold=event.severe_threshold,
        unit=event.unit,
        p10=event.p10,
        median=event.median,
        p90=event.p90,
    )


async def save_risk_run(
    session: AsyncSession,
    *,
    field_id: int,
    meta: EnsembleForecastMeta,
    outlook: RiskOutlook,
) -> StoredRiskRun:
    """Persist one accepted run and all of its signals in one transaction."""

    if not outlook.available:
        raise ValueError("Only scientifically accepted risk runs may be persisted")
    if outlook.generated_for_date is None:
        raise ValueError("Risk outlook has no analysis date")

    retrieved_at = _utc_naive(meta.retrieved_at)
    existing = await _find_run(
        session,
        field_id=field_id,
        model=meta.model,
        retrieved_at=retrieved_at,
    )
    if existing is not None:
        return _stored(existing, created=False)

    run = RiskForecastRun(
        field_id=field_id,
        source=meta.source,
        model=meta.model,
        retrieved_at=retrieved_at,
        analysis_date=outlook.generated_for_date,
        timezone=meta.timezone,
        member_count=meta.member_count,
        forecast_days=outlook.forecast_days,
        valid_days=outlook.valid_days,
        incomplete_days=outlook.incomplete_days,
        status=outlook.status,
        signals=[_signal_model(event) for event in outlook.events],
    )
    try:
        session.add(run)
        await session.flush()
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await _find_run(
            session,
            field_id=field_id,
            model=meta.model,
            retrieved_at=retrieved_at,
        )
        if existing is None:
            raise
        return _stored(existing, created=False)

    return _stored(run, created=True)


async def set_signal_delivery(
    session: AsyncSession,
    *,
    signal_id: int,
    state: DeliveryState,
    notified_at: datetime | None = None,
) -> bool:
    if state not in _ALLOWED_DELIVERY_STATES:
        raise ValueError(f"Unsupported delivery state: {state}")

    result = await session.execute(
        update(RiskForecastSignal)
        .where(RiskForecastSignal.id == signal_id)
        .values(
            delivery_state=state,
            notified_at=(
                None if notified_at is None else _utc_naive(notified_at)
            ),
        )
    )
    await session.commit()
    return bool(result.rowcount)


def _signal_snapshot(signal: RiskForecastSignal) -> RiskSignalSnapshot:
    return RiskSignalSnapshot(
        signal_id=signal.id,
        risk_type=cast(RiskType, signal.risk_type),
        event_date=signal.event_date,
        lead_days=signal.lead_days,
        level=cast(RiskLevel, signal.level),
        members_exceeding=signal.members_exceeding,
        valid_members=signal.valid_members,
        member_fraction=signal.member_fraction,
        severe_member_fraction=signal.severe_member_fraction,
        threshold=signal.threshold,
        severe_threshold=signal.severe_threshold,
        unit=signal.unit,
        p10=signal.p10,
        median=signal.median,
        p90=signal.p90,
        delivery_state=signal.delivery_state,
        notified_at=signal.notified_at,
    )


def _run_snapshot(run: RiskForecastRun) -> RiskRunSnapshot:
    signals = sorted(
        run.signals,
        key=lambda signal: (signal.event_date, signal.risk_type, signal.id),
    )
    return RiskRunSnapshot(
        run_id=run.id,
        field_id=run.field_id,
        source=run.source,
        model=run.model,
        retrieved_at=run.retrieved_at,
        analysis_date=run.analysis_date,
        timezone=run.timezone,
        member_count=run.member_count,
        forecast_days=run.forecast_days,
        valid_days=run.valid_days,
        incomplete_days=run.incomplete_days,
        status=run.status,
        signals=tuple(_signal_snapshot(signal) for signal in signals),
    )


async def list_recent_risk_runs(
    session: AsyncSession,
    *,
    field_id: int,
    limit: int = 2,
) -> tuple[RiskRunSnapshot, ...]:
    if limit <= 0 or limit > 20:
        raise ValueError("limit must be between 1 and 20")

    result = await session.execute(
        select(RiskForecastRun)
        .options(selectinload(RiskForecastRun.signals))
        .where(RiskForecastRun.field_id == field_id)
        .order_by(RiskForecastRun.retrieved_at.desc(), RiskForecastRun.id.desc())
        .limit(limit)
    )
    return tuple(_run_snapshot(run) for run in result.scalars().all())


async def prune_risk_runs_before(
    session: AsyncSession,
    *,
    cutoff: datetime,
) -> int:
    """Delete old runs and their signals without relying on SQLite FK pragmas."""

    cutoff_utc = _utc_naive(cutoff)
    result = await session.execute(
        select(RiskForecastRun.id).where(RiskForecastRun.retrieved_at < cutoff_utc)
    )
    run_ids = tuple(result.scalars().all())
    if not run_ids:
        return 0

    await session.execute(
        delete(RiskForecastSignal).where(RiskForecastSignal.run_id.in_(run_ids))
    )
    await session.execute(
        delete(RiskForecastRun).where(RiskForecastRun.id.in_(run_ids))
    )
    await session.commit()
    return len(run_ids)
