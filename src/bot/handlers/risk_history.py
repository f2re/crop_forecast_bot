from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.risk_history import load_risk_history
from src.bot.keyboards import get_main_keyboard
from src.bot.risk_history import format_risk_history
from src.database.crud import get_field_context

router = Router(name="risk-history")


async def _build_text(session: AsyncSession, telegram_id: int) -> str:
    context = await get_field_context(session, telegram_id)
    if context is None:
        return (
            "Сначала добавьте поле и выберите культуру. История появится после "
            "успешного фонового анализа погодных рисков."
        )

    history = await load_risk_history(session, field_id=context.field_id)
    return format_risk_history(
        history,
        field_name=context.field_name,
        crop=context.crop_key,
    )


@router.callback_query(F.data == "risk_history")
async def show_risk_history(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    text = await _build_text(session, callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=get_main_keyboard())


@router.message(Command("history"))
async def risk_history_command(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    text = await _build_text(session, message.from_user.id)
    await message.answer(text, reply_markup=get_main_keyboard())
