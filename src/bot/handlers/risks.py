from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.risk import RiskForecastProviderError
from src.application.risk_overview import generate_risk_overview
from src.bot.keyboards import get_main_keyboard
from src.bot.risk_overview import format_risk_overview
from src.database.crud import get_field_context
from src.domain.season import local_today

logger = logging.getLogger(__name__)
router = Router(name="risks")


async def _build_text(session: AsyncSession, telegram_id: int) -> str:
    context = await get_field_context(session, telegram_id)
    if context is None:
        return (
            "Сначала добавьте поле и выберите культуру. Затем откройте "
            "«Погодные риски»."
        )

    overview = await generate_risk_overview(
        context.latitude,
        context.longitude,
        as_of_date=local_today(context.timezone),
    )
    return format_risk_overview(
        overview,
        field_name=context.field_name,
        crop=context.crop_key,
        phase=context.phenological_phase,
    )


@router.callback_query(F.data == "risk_overview")
async def show_risk_overview(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    await callback.message.edit_text(
        "⏳ Проверяю ансамблевые сценарии для активного поля…"
    )
    try:
        text = await _build_text(session, callback.from_user.id)
    except (RiskForecastProviderError, ValueError) as exc:
        logger.warning(
            "Manual risk overview unavailable for user %s: %s",
            callback.from_user.id,
            exc,
        )
        text = (
            "⚠️ <b>Погодные риски сейчас не оценены</b>\n\n"
            f"Причина: {html.escape(str(exc))}.\n"
            "Отсутствие данных не означает отсутствие риска. Проверьте "
            "официальный прогноз и повторите запрос после обновления данных."
        )

    await callback.message.edit_text(text, reply_markup=get_main_keyboard())


@router.message(Command("risks"))
async def risk_overview_command(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    await message.answer("⏳ Проверяю ансамблевые сценарии для активного поля…")
    try:
        text = await _build_text(session, message.from_user.id)
    except (RiskForecastProviderError, ValueError) as exc:
        logger.warning(
            "Manual risk overview unavailable for user %s: %s",
            message.from_user.id,
            exc,
        )
        text = (
            "⚠️ <b>Погодные риски сейчас не оценены</b>\n\n"
            f"Причина: {html.escape(str(exc))}.\n"
            "Отсутствие данных не означает отсутствие риска. Проверьте "
            "официальный прогноз и повторите запрос после обновления данных."
        )
    await message.answer(text, reply_markup=get_main_keyboard())
