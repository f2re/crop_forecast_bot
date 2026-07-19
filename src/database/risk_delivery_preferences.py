from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Field, User
from src.domain.risk_delivery import (
    RiskDeliveryMode,
    validate_quiet_hours,
    validate_risk_delivery_mode,
)


@dataclass(frozen=True, slots=True)
class RiskDeliveryPreferences:
    field_id: int
    mode: RiskDeliveryMode
    quiet_hours_start: int | None
    quiet_hours_end: int | None


def _snapshot(field: Field) -> RiskDeliveryPreferences:
    return RiskDeliveryPreferences(
        field_id=field.id,
        mode=validate_risk_delivery_mode(field.risk_delivery_mode),
        quiet_hours_start=field.quiet_hours_start,
        quiet_hours_end=field.quiet_hours_end,
    )


async def _owned_field(
    session: AsyncSession,
    *,
    telegram_id: int,
    field_id: int,
    lock: bool,
) -> Field:
    statement = (
        select(Field)
        .join(User, User.id == Field.user_id)
        .where(User.telegram_id == telegram_id, Field.id == field_id)
    )
    if lock:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    field = result.scalar_one_or_none()
    if field is None:
        raise ValueError("Поле не найдено или недоступно пользователю.")
    return field


async def get_risk_delivery_preferences(
    session: AsyncSession,
    *,
    telegram_id: int,
    field_id: int,
) -> RiskDeliveryPreferences:
    field = await _owned_field(
        session,
        telegram_id=telegram_id,
        field_id=field_id,
        lock=False,
    )
    return _snapshot(field)


async def set_risk_delivery_mode(
    session: AsyncSession,
    *,
    telegram_id: int,
    field_id: int,
    mode: str,
) -> RiskDeliveryPreferences:
    resolved = validate_risk_delivery_mode(mode)
    field = await _owned_field(
        session,
        telegram_id=telegram_id,
        field_id=field_id,
        lock=True,
    )
    field.risk_delivery_mode = resolved
    field.updated_at = datetime.utcnow()
    await session.commit()
    return _snapshot(field)


async def set_risk_quiet_hours(
    session: AsyncSession,
    *,
    telegram_id: int,
    field_id: int,
    start_hour: int | None,
    end_hour: int | None,
) -> RiskDeliveryPreferences:
    start_hour, end_hour = validate_quiet_hours(start_hour, end_hour)
    field = await _owned_field(
        session,
        telegram_id=telegram_id,
        field_id=field_id,
        lock=True,
    )
    field.quiet_hours_start = start_hour
    field.quiet_hours_end = end_hour
    field.updated_at = datetime.utcnow()
    await session.commit()
    return _snapshot(field)
