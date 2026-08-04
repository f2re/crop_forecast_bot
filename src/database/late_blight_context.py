"""Persistence operations for user-provided late-blight inoculum context."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.biological_monitoring import (
    LateBlightMonitorContext,
    biological_monitors,
    get_active_late_blight_context,
)
from src.domain.late_blight_delivery import validate_inoculum_context


async def set_late_blight_inoculum_context(
    session: AsyncSession,
    telegram_id: int,
    value: str,
) -> LateBlightMonitorContext:
    """Store context for the user's enabled active-season monitor.

    The delivered semantic state is intentionally not rewritten here. The next
    manual view or scheduler run compares the old state with the new context and
    can produce a visible context-confirmed/context-cleared transition.
    """

    resolved = validate_inoculum_context(value)
    context = await get_active_late_blight_context(session, telegram_id)
    if context is None:
        raise ValueError("Сначала добавьте поле и выберите культуру.")
    if context.crop_key != "potato":
        raise ValueError("Контекст фитофтороза сейчас доступен только для картофеля.")
    if context.monitor_id is None or not context.enabled:
        raise ValueError("Сначала включите фоновые предупреждения о фитофторозе.")
    if context.inoculum_context == resolved:
        return context

    result = await session.execute(
        update(biological_monitors)
        .where(biological_monitors.c.id == context.monitor_id)
        .values(
            inoculum_context=resolved,
            updated_at=datetime.utcnow(),
        )
    )
    if result.rowcount != 1:
        await session.rollback()
        raise RuntimeError("Не удалось сохранить контекст источника фитофтороза.")
    await session.commit()

    saved = await get_active_late_blight_context(session, telegram_id)
    if saved is None or saved.monitor_id != context.monitor_id:
        raise RuntimeError("Наблюдение исчезло после сохранения контекста.")
    return saved
