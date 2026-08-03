from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.biological_monitoring import (
    LateBlightMonitorContext,
    save_late_blight_delivery_state,
)
from src.domain.late_blight import LateBlightOutlook
from src.domain.late_blight_delivery import (
    LateBlightDeliveryDecision,
    plan_late_blight_delivery,
)


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
