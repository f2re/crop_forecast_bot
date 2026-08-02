from __future__ import annotations

import html
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from src.agro.crop_catalog import get_crop_name
from src.bot.calendar import (
    build_season_calendar,
    parse_calendar_date,
    parse_calendar_month,
)
from src.bot.keyboards import get_field_keyboard, get_main_keyboard, get_season_keyboard
from src.bot.telegram_text import answer_html, edit_html
from src.database.crud import get_field_context, set_season_start
from src.domain.season import local_today, parse_season_date

router = Router(name="season-calendar")


class SeasonCalendarStates(StatesGroup):
    waiting_for_manual_date = State()


def _season_text(context) -> str:
    start = (
        context.season_start_date.strftime("%d.%m.%Y")
        if context.season_start_date
        else "не задана"
    )
    phase = html.escape(context.phenological_phase) if context.phenological_phase else "не указана"
    return (
        "📅 <b>Сезон выбранной культуры</b>\n"
        f"🗺 Поле: {html.escape(context.field_name)}\n"
        f"🌱 Культура для отчёта: "
        f"<b>{html.escape(get_crop_name(context.crop_key))}</b>\n"
        f"📆 Посев/начало сезона: {start}\n"
        f"🌿 Фаза: {phase}\n\n"
        "Дата и фаза задаются отдельно для каждой культуры на этой точке. "
        "Переключить культуру можно в разделе «Культуры поля»."
    )


async def _save_date(
    session: AsyncSession,
    telegram_id: int,
    value: date,
    *,
    timezone_name: str,
) -> None:
    validated = parse_season_date(
        value.isoformat(),
        today=local_today(timezone_name),
    )
    await set_season_start(session, telegram_id, validated)


@router.callback_query(F.data == "season")
async def show_selected_crop_season(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    context = await get_field_context(session, callback.from_user.id)
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
    await edit_html(
        callback.message,
        _season_text(context),
        reply_markup=get_season_keyboard(
            has_start=context.season_start_date is not None,
            has_phase=context.phenological_phase is not None,
        ),
    )


@router.callback_query(F.data == "season_start_set")
async def open_season_calendar(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    await state.clear()
    today = local_today(context.timezone)
    display = context.season_start_date or today
    await callback.answer()
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        "📅 <b>Выберите дату посева или начала сезона</b>\n"
        f"Поле: {html.escape(context.field_name)}\n"
        f"Культура: {html.escape(get_crop_name(context.crop_key))}\n\n"
        "Будущие даты недоступны. Для озимых можно перейти к прошлому году.",
        reply_markup=build_season_calendar(
            display,
            today=today,
            selected=context.season_start_date,
        ),
    )


@router.callback_query(F.data == "season_calendar:noop")
async def calendar_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("season_calendar:nav:"))
async def navigate_season_calendar(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Поле не найдено", show_alert=True)
        return
    try:
        display = parse_calendar_month(callback.data or "")
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    today = local_today(context.timezone)
    await callback.answer()
    if callback.message is None:
        return
    await callback.message.edit_reply_markup(
        reply_markup=build_season_calendar(
            display,
            today=today,
            selected=context.season_start_date,
        )
    )


@router.callback_query(F.data.startswith("season_calendar:pick:"))
async def pick_season_date(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Поле не найдено", show_alert=True)
        return
    try:
        value = parse_calendar_date(callback.data or "")
        await _save_date(
            session,
            callback.from_user.id,
            value,
            timezone_name=context.timezone,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.clear()
    await callback.answer("Дата сохранена")
    updated = await get_field_context(session, callback.from_user.id)
    if callback.message is None or updated is None:
        return
    await edit_html(
        callback.message,
        f"✅ <b>Дата сохранена: {value:%d.%m.%Y}</b>\n"
        f"Поле: {html.escape(updated.field_name)}\n"
        f"Культура: {html.escape(get_crop_name(updated.crop_key))}\n\n"
        "ГДД и сезонные накопления будут считаться от этой даты при полном "
        "покрытии метеорологического ряда.",
        reply_markup=get_season_keyboard(
            has_start=True,
            has_phase=updated.phenological_phase is not None,
        ),
    )


@router.callback_query(F.data == "season_calendar:manual")
async def request_manual_season_date(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.set_state(SeasonCalendarStates.waiting_for_manual_date)
    await callback.answer()
    if callback.message is None:
        return
    await answer_html(
        callback.message,
        "⌨️ Введите дату: <code>ДД.ММ.ГГГГ</code> или "
        "<code>ГГГГ-ММ-ДД</code>.\nДля отмены отправьте /cancel.",
    )


@router.message(SeasonCalendarStates.waiting_for_manual_date, Command("cancel"))
@router.message(
    SeasonCalendarStates.waiting_for_manual_date,
    F.text.casefold() == "отмена",
)
async def cancel_manual_season_date(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ввод даты отменён.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=get_main_keyboard())


@router.message(SeasonCalendarStates.waiting_for_manual_date, F.text)
async def receive_manual_season_date(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return
    context = await get_field_context(session, message.from_user.id)
    if context is None:
        await state.clear()
        await message.answer("Сначала добавьте поле.", reply_markup=get_field_keyboard())
        return
    try:
        value = parse_season_date(
            message.text or "",
            today=local_today(context.timezone),
        )
        await set_season_start(session, message.from_user.id, value)
    except ValueError as exc:
        await message.answer(f"❌ {exc}")
        return
    await state.clear()
    await message.answer(
        f"✅ Дата для культуры «{get_crop_name(context.crop_key)}»: "
        f"{value:%d.%m.%Y}",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Выберите действие:", reply_markup=get_main_keyboard())


@router.callback_query(F.data == "season_calendar:cancel")
async def close_season_calendar(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    context = await get_field_context(session, callback.from_user.id)
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
    await edit_html(
        callback.message,
        _season_text(context),
        reply_markup=get_season_keyboard(
            has_start=context.season_start_date is not None,
            has_phase=context.phenological_phase is not None,
        ),
    )
