from __future__ import annotations

from typing import cast

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import get_field_keyboard, get_report_help_keyboard
from src.bot.report_help import ReportHelpTopic, format_report_help
from src.bot.telegram_text import edit_html
from src.database.crud import get_field_context
from src.database.phenology import get_active_crop_phenology
from src.domain.season import local_today

router = Router(name="report-help")
_ALLOWED_TOPICS = frozenset({"heat", "water", "htc", "phase", "sources", "risk"})


@router.callback_query(F.data.startswith("report_help:"))
async def show_report_help(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    raw_topic = (callback.data or "").partition(":")[2]
    if raw_topic not in _ALLOWED_TOPICS:
        await callback.answer("Раздел справки не найден", show_alert=True)
        return

    context = await get_field_context(session, callback.from_user.id)
    phenology = await get_active_crop_phenology(session, callback.from_user.id)
    await callback.answer()
    if callback.message is None:
        return
    if context is None:
        await edit_html(
            callback.message,
            "Сначала добавьте поле.",
            reply_markup=get_field_keyboard(),
        )
        return

    topic = cast(ReportHelpTopic, raw_topic)
    text = format_report_help(
        topic,
        crop_key=context.crop_key,
        season_start_date=context.season_start_date,
        current_phase=context.phenological_phase,
        today=local_today(context.timezone),
        date_basis=(phenology.date_basis if phenology is not None else None),
        production_system=(
            phenology.production_system if phenology is not None else None
        ),
        plant_type=(phenology.plant_type if phenology is not None else None),
        phase_confirmed_at=(
            phenology.phase_confirmed_at if phenology is not None else None
        ),
        timezone_name=context.timezone,
    )
    back_callback = "risk_overview" if topic == "risk" else "agro_report"
    await edit_html(
        callback.message,
        text,
        reply_markup=get_report_help_keyboard(back_callback=back_callback),
    )
