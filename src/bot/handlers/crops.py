from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.agro.crop_catalog import CROPS, get_crop_name
from src.bot.crop_keyboards import (
    get_crop_add_categories_keyboard,
    get_crop_add_list_keyboard,
    get_crop_manager_keyboard,
)
from src.bot.keyboards import get_field_keyboard, get_main_keyboard
from src.bot.telegram_text import answer_html, edit_html
from src.database.crops import (
    add_or_select_crop,
    list_field_crops,
    remove_field_crop,
    select_field_crop,
)
from src.database.crud import get_field_context

router = Router(name="crops")


def _manager_text(context, crops) -> str:
    names = ", ".join(get_crop_name(item.crop_key) for item in crops)
    selected = next((item for item in crops if item.is_selected), None)
    selected_name = get_crop_name(selected.crop_key) if selected else "не выбрана"
    return (
        "🌱 <b>Культуры на этой точке</b>\n"
        f"🗺 Поле: {html.escape(context.field_name)}\n"
        f"Посеяно/выращивается: {html.escape(names or 'не указано')}\n\n"
        f"✅ Для отчёта, даты и фазы сейчас выбрана: "
        f"<b>{html.escape(selected_name)}</b>.\n\n"
        "Погодный прогноз относится ко всей точке. Дата посева и фактическая "
        "фаза хранятся отдельно для каждой культуры."
    )


async def _show_manager(
    message,
    session: AsyncSession,
    telegram_id: int,
) -> None:
    context = await get_field_context(session, telegram_id)
    if context is None:
        await edit_html(
            message,
            "Сначала добавьте поле.",
            reply_markup=get_field_keyboard(),
        )
        return
    crops = await list_field_crops(session, telegram_id, field_id=context.field_id)
    await edit_html(
        message,
        _manager_text(context, crops),
        reply_markup=get_crop_manager_keyboard(crops),
    )


@router.callback_query(F.data.in_({"crop_choose", "crop_manage"}))
async def manage_crops(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await _show_manager(callback.message, session, callback.from_user.id)


@router.message(Command("crops"))
async def manage_crops_command(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    context = await get_field_context(session, message.from_user.id)
    if context is None:
        await message.answer("Сначала добавьте поле.", reply_markup=get_field_keyboard())
        return
    crops = await list_field_crops(
        session,
        message.from_user.id,
        field_id=context.field_id,
    )
    await answer_html(
        message,
        _manager_text(context, crops),
        reply_markup=get_crop_manager_keyboard(crops),
    )


@router.callback_query(F.data == "crop_add")
async def add_crop_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        "➕ <b>Добавить культуру на поле</b>\n"
        f"Точка: {html.escape(context.field_name)}\n\n"
        "Выберите категорию. Уже добавленная культура просто станет выбранной "
        "для отчёта — дубликат не создаётся.",
        reply_markup=get_crop_add_categories_keyboard(),
    )


@router.callback_query(F.data.startswith("crop_add_cat:"))
@router.callback_query(F.data.startswith("crop_cat:"))
async def add_crop_category(callback: CallbackQuery) -> None:
    try:
        category_id = (callback.data or "").split(":", 1)[1]
    except IndexError:
        await callback.answer("Некорректная категория", show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        "Выберите культуру:",
        reply_markup=get_crop_add_list_keyboard(category_id),
    )


@router.callback_query(F.data.startswith("crop_add_pick:"))
@router.callback_query(F.data.startswith("crop_pick:"))
async def add_crop(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        crop_key = (callback.data or "").split(":", 1)[1]
    except IndexError:
        await callback.answer("Некорректная культура", show_alert=True)
        return
    if crop_key not in CROPS:
        await callback.answer("Неизвестная культура", show_alert=True)
        return
    try:
        profile = await add_or_select_crop(
            session,
            callback.from_user.id,
            crop_key,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Культура добавлена и выбрана")
    if callback.message is None:
        return
    await _show_manager(callback.message, session, callback.from_user.id)
    if profile.season_start_date is None:
        await answer_html(
            callback.message,
            f"📅 Для культуры <b>{html.escape(get_crop_name(crop_key))}</b> "
            "ещё не указана дата посева. Откройте «Сезон и фаза».",
            reply_markup=get_main_keyboard(),
        )


@router.callback_query(F.data.startswith("crop_select:"))
async def select_crop(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        season_id = int((callback.data or "").split(":", 1)[1])
        profile = await select_field_crop(
            session,
            callback.from_user.id,
            season_id,
        )
    except (ValueError, IndexError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer(f"Выбрано: {get_crop_name(profile.crop_key)}")
    if callback.message is not None:
        await _show_manager(callback.message, session, callback.from_user.id)


@router.callback_query(F.data.startswith("crop_remove:"))
async def remove_crop(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        season_id = int((callback.data or "").split(":", 1)[1])
        selected = await remove_field_crop(
            session,
            callback.from_user.id,
            season_id,
        )
    except (ValueError, IndexError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer(
        f"Культура удалена. Выбрано: {get_crop_name(selected.crop_key)}"
    )
    if callback.message is not None:
        await _show_manager(callback.message, session, callback.from_user.id)
