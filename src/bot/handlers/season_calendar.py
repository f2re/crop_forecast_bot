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
from src.bot.keyboards import (
    get_date_basis_keyboard,
    get_field_keyboard,
    get_main_keyboard,
    get_season_keyboard,
)
from src.bot.telegram_text import answer_html, edit_html
from src.database.crud import get_field_context
from src.database.phenology import (
    get_active_crop_phenology,
    set_season_date_with_basis,
)
from src.domain.phenology import date_basis_label, validate_date_basis
from src.domain.season import local_today, parse_season_date

router = Router(name="season-calendar")


class SeasonCalendarStates(StatesGroup):
    waiting_for_manual_date = State()
    waiting_for_date_basis = State()


def _season_text(context, phenology) -> str:
    start = (
        context.season_start_date.strftime("%d.%m.%Y")
        if context.season_start_date
        else "не задана"
    )
    phase = (
        html.escape(context.phenological_phase)
        if context.phenological_phase
        else "не указана"
    )
    basis = date_basis_label(
        phenology.date_basis if phenology is not None else "season_start"
    )
    confirmation = ""
    if phenology is not None and phenology.phase_confirmed_at is not None:
        confirmation = "\n✅ Дата последнего подтверждения стадии сохранена."
    return (
        "📅 <b>Дата и стадия выбранной культуры</b>\n"
        f"🗺 Поле: {html.escape(context.field_name)}\n"
        f"🌱 Культура для отчёта: "
        f"<b>{html.escape(get_crop_name(context.crop_key))}</b>\n"
        f"📆 Указанная дата: {start}\n"
        f"🧭 Что означает дата: {html.escape(basis)}\n"
        f"🌿 Наблюдаемая стадия: {phase}{confirmation}\n\n"
        "Дата, её смысл и стадия хранятся отдельно для каждой культуры. "
        "Бот не меняет стадию без подтверждения после осмотра растений."
    )


async def _show_date_basis_choice(
    message: Message,
    state: FSMContext,
    *,
    value: date,
    field_name: str,
    crop_key: str,
) -> None:
    await state.update_data(pending_season_date=value.isoformat())
    await state.set_state(SeasonCalendarStates.waiting_for_date_basis)
    await edit_html(
        message,
        f"📅 <b>Дата: {value:%d.%m.%Y}</b>\n"
        f"Поле: {html.escape(field_name)}\n"
        f"Культура: {html.escape(get_crop_name(crop_key))}\n\n"
        "Что произошло в эту дату? Это важно: посев, всходы и высадка "
        "рассады — разные точки отсчёта.",
        reply_markup=get_date_basis_keyboard(),
    )


@router.callback_query(F.data == "season")
async def show_selected_crop_season(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
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
    await edit_html(
        callback.message,
        _season_text(context, phenology),
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
        "📅 <b>Выберите исходную дату</b>\n"
        f"Поле: {html.escape(context.field_name)}\n"
        f"Культура: {html.escape(get_crop_name(context.crop_key))}\n\n"
        "После выбора бот спросит, что означает дата: посев, всходы, "
        "высадка рассады или начало наблюдений. Будущие даты недоступны.",
        reply_markup=build_season_calendar(
            display,
            today=today,
            selected=context.season_start_date,
        ),
    )


@router.callback_query(F.data == "season_calendar:noop")
@router.callback_query(F.data == "phenology:noop")
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
        value = parse_season_date(
            value.isoformat(),
            today=local_today(context.timezone),
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    await _show_date_basis_choice(
        callback.message,
        state,
        value=value,
        field_name=context.field_name,
        crop_key=context.crop_key,
    )


@router.callback_query(F.data.startswith("season_basis:"))
async def save_date_basis(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    raw_basis = (callback.data or "").partition(":")[2]
    try:
        basis = validate_date_basis(raw_basis)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    data = await state.get_data()
    raw_date = data.get("pending_season_date")
    if not isinstance(raw_date, str):
        await callback.answer(
            "Дата не найдена. Откройте календарь ещё раз.",
            show_alert=True,
        )
        return
    try:
        value = date.fromisoformat(raw_date)
        saved = await set_season_date_with_basis(
            session,
            callback.from_user.id,
            value,
            basis,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    await callback.answer("Дата и её смысл сохранены")
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        f"✅ <b>Дата сохранена: {value:%d.%m.%Y}</b>\n"
        f"Культура: {html.escape(get_crop_name(saved.crop_key))}\n"
        f"Смысл даты: <b>{html.escape(date_basis_label(saved.date_basis))}</b>.\n\n"
        "Накопленное тепло и сезонные суммы считаются от этой даты. "
        "Прежняя стадия очищена: подтвердите фактическую стадию после осмотра.",
        reply_markup=get_season_keyboard(has_start=True, has_phase=False),
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
    except ValueError as exc:
        await message.answer(f"❌ {exc}")
        return

    await state.update_data(pending_season_date=value.isoformat())
    await state.set_state(SeasonCalendarStates.waiting_for_date_basis)
    await message.answer(
        f"✅ Дата принята: <b>{value:%d.%m.%Y}</b>.\n"
        "Теперь укажите, что произошло в эту дату.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Выберите смысл даты:",
        reply_markup=get_date_basis_keyboard(),
    )


@router.callback_query(F.data == "season_calendar:cancel")
async def close_season_calendar(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
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
    await edit_html(
        callback.message,
        _season_text(context, phenology),
        reply_markup=get_season_keyboard(
            has_start=context.season_start_date is not None,
            has_phase=context.phenological_phase is not None,
        ),
    )
