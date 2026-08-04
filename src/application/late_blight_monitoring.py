from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.biological_monitoring import (
    LateBlightMonitorContext,
    enable_late_blight_monitor,
    get_active_late_blight_context,
    save_late_blight_delivery_state,
)
from src.database.phenology import get_active_crop_phenology
from src.domain.late_blight import LateBlightOutlook
from src.domain.late_blight_delivery import (
    LateBlightDeliveryDecision,
    plan_late_blight_delivery,
)

_OPEN_FIELD_UNKNOWN_MESSAGE = (
    "Сначала укажите «Открытый грунт» в разделе «Сезон и фаза → "
    "Условия выращивания». Hutton использует наружную модельную погоду."
)
_GREENHOUSE_MESSAGE = (
    "Hutton по наружной погоде не применяется к защищённому грунту. "
    "Для теплицы нужен отдельный расчёт по датчику внутри сооружения."
)


async def require_open_field_late_blight_scope(
    session: AsyncSession,
    telegram_id: int,
) -> None:
    """Reject outdoor Hutton use when the crop is not confirmed open-field."""

    profile = await get_active_crop_phenology(session, telegram_id)
    if profile is None:
        raise ValueError("Сначала добавьте поле и выберите культуру.")
    if profile.crop_key != "potato":
        raise ValueError("Наблюдение Hutton сейчас доступно только для картофеля.")
    if profile.production_system == "greenhouse":
        raise ValueError(_GREENHOUSE_MESSAGE)
    if profile.production_system != "open_field":
        raise ValueError(_OPEN_FIELD_UNKNOWN_MESSAGE)


async def enable_open_field_late_blight_monitor(
    session: AsyncSession,
    telegram_id: int,
) -> LateBlightMonitorContext:
    await require_open_field_late_blight_scope(session, telegram_id)
    return await enable_late_blight_monitor(session, telegram_id)


async def acknowledge_manual_late_blight_view(
    session: AsyncSession,
    context: LateBlightMonitorContext,
    outlook: LateBlightOutlook,
    *,
    now_utc: datetime | None = None,
) -> LateBlightDeliveryDecision | None:
    """Treat a successful manual report as delivery of its semantic state.

    This prevents an enabled background monitor from sending the same period
    again shortly after the user has explicitly opened and read it.
    """

    if context.monitor_id is None or not context.enabled:
        return None
    current_utc = now_utc or datetime.now(timezone.utc)
    if current_utc.tzinfo is None or current_utc.utcoffset() is None:
        current_utc = current_utc.replace(tzinfo=timezone.utc)
    local_now = current_utc.astimezone(ZoneInfo(context.timezone))
    decision = plan_late_blight_delivery(
        outlook.periods,
        previous_state=context.delivery_state,
        inoculum_context=context.inoculum_context,
        mode="immediate",
        local_datetime=local_now,
        quiet_hours_start=None,
        quiet_hours_end=None,
    )
    await save_late_blight_delivery_state(
        session,
        monitor_ids=(context.monitor_id,),
        state=decision.current_state,
        checked_local_date=local_now.date(),
        observed_at=outlook.retrieved_at,
        notified_at=current_utc if decision.change is not None else None,
    )
    return decision


async def load_open_field_late_blight_context(
    session: AsyncSession,
    telegram_id: int,
) -> LateBlightMonitorContext:
    """Validate scope and return the active monitor context for UI services."""

    await require_open_field_late_blight_scope(session, telegram_id)
    context = await get_active_late_blight_context(session, telegram_id)
    if context is None:
        raise ValueError("Сначала добавьте поле и выберите культуру.")
    return context
