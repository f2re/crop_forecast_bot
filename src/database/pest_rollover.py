from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.pest_monitoring import PestMonitor
from src.domain.pests import PestModel


async def rollover_calendar_pest_monitor(
    session: AsyncSession,
    monitor_id: int,
    *,
    model: PestModel,
    biofix_date: date,
) -> bool:
    """Move a calendar-start monitor to its current model year.

    Observation-start models are deliberately rejected: a real field event may
    never be replaced by an automatically generated date.
    """

    if model.biofix_mode != "calendar":
        raise ValueError("Автоматическое обновление допустимо только для календарной модели.")

    result = await session.execute(
        select(PestMonitor).where(PestMonitor.id == monitor_id).with_for_update()
    )
    monitor = result.scalar_one_or_none()
    if monitor is None:
        return False
    if monitor.pest_key != model.key:
        raise ValueError("Наблюдение относится к другой модели вредителя.")

    changed = (
        monitor.biofix_date != biofix_date
        or monitor.biofix_type != model.biofix_type
        or monitor.model_version != model.model_version
    )
    if not changed:
        await session.rollback()
        return False

    monitor.biofix_date = biofix_date
    monitor.biofix_type = model.biofix_type
    monitor.model_version = model.model_version
    monitor.last_checked_local_date = None
    monitor.last_notified_stage = None
    monitor.last_notified_advance = None
    monitor.last_notified_at = None
    monitor.updated_at = datetime.utcnow()
    await session.commit()
    return True
