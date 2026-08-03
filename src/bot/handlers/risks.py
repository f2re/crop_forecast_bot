from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.risk import RiskForecastProviderError
from src.application.risk_overview import generate_risk_overview
from src.bot.keyboards import get_risk_result_keyboard
from src.bot.risk_overview import format_risk_overview
from src.bot.telegram_text import answer_html, edit_html
from src.database.crops import list_field_crop_keys
from src.database.crud import get_field_context
from src.domain.season import local_today

logger = logging.getLogger(__name__)
router = Router(name="risks")


async def _build_text(session: AsyncSession, telegram_id: int) -> str:
    context = await get_field_context(session, telegram_id)
    if context is None:
        return (
            "Сначала добавьте поле и хотя бы одну культуру. Затем откройте "
            "«Погодные условия»."
        )

    overview = await generate_risk_overview(
        context.latitude,
        context.longitude,
        as_of_date=local_today(context.timezone),
    )
    crop_keys = await list_field_crop_keys(session, context.field_id)
    return format_risk_overview(
        overview,
        field_name=context.field_name,
        crop=context.crop_key,
        crops=crop_keys,
        phase=context.phenological_phase,
    )


def _unavailable_text(exc: Exception) -> str:
    return (
        "⚠️ <b>Погодные условия сейчас не оценены</b>\n\n"
        f"Причина: {html.escape(str(exc))}.\n"
        "Отсутствие данных не означает отсутствие опасного явления. Проверьте "
        "официальный прогноз и повторите запрос после обновления данных."
    )


@router.callback_query(F.data == "risk_overview")
async def show_risk_overview(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    await edit_html(
        callback.message,
        "⏳ Получаю 31 вариант прогноза и объединяю одинаковые условия "
        "по периодам…",
    )
    try:
        text = await _build_text(session, callback.from_user.id)
    except (RiskForecastProviderError, ValueError) as exc:
        logger.warning(
            "Manual risk overview unavailable for user %s: %s",
            callback.from_user.id,
            exc,
        )
        text = _unavailable_text(exc)

    await edit_html(
        callback.message,
        text,
        reply_markup=get_risk_result_keyboard(),
    )


@router.message(Command("risks"))
async def risk_overview_command(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    await message.answer(
        "⏳ Получаю 31 вариант прогноза и объединяю одинаковые условия "
        "по периодам…"
    )
    try:
        text = await _build_text(session, message.from_user.id)
    except (RiskForecastProviderError, ValueError) as exc:
        logger.warning(
            "Manual risk overview unavailable for user %s: %s",
            message.from_user.id,
            exc,
        )
        text = _unavailable_text(exc)
    await answer_html(message, text, reply_markup=get_risk_result_keyboard())
