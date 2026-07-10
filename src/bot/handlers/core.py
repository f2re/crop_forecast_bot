from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from src.agro.crop_catalog import CROPS, get_crop_name
from src.api.open_meteo import OpenMeteoError
from src.application.agro_report import generate_agro_report
from src.bot.keyboards import (
    get_crop_categories_keyboard,
    get_crop_list_keyboard,
    get_field_keyboard,
    get_location_reply_keyboard,
    get_main_keyboard,
    get_settings_keyboard,
)
from src.database.crud import (
    get_or_create_user,
    get_user,
    save_coordinates,
    set_daily_digest,
    update_user_crop,
)
from src.domain.coordinates import Coordinates, parse_coordinates

logger = logging.getLogger(__name__)
router = Router(name="core")

_HELP_TEXT = (
    "🆘 <b>Как пользоваться ботом</b>\n\n"
    "1️⃣ Откройте «Моё поле» и отправьте геолокацию или координаты.\n"
    "2️⃣ Выберите культуру.\n"
    "3️⃣ Нажмите «Агропрогноз».\n\n"
    "Отчёт показывает оперативную оценку температуры, влагообеспеченности, "
    "ГДД и риска заморозка. В каждом отчёте указаны источник и ограничения.\n\n"
    "<b>Команды</b>\n"
    "/start — главное меню\n"
    "/help — эта справка\n"
    "/cancel — отменить текущий ввод"
)


class FieldStates(StatesGroup):
    waiting_for_coordinates = State()


async def _save_field(message: Message, session: AsyncSession, coords: Coordinates) -> None:
    if message.from_user is None:
        return
    await save_coordinates(
        session,
        telegram_id=message.from_user.id,
        latitude=coords.latitude,
        longitude=coords.longitude,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    await message.answer(
        f"✅ Поле сохранено: <b>{coords.latitude:.5f}, {coords.longitude:.5f}</b>\n"
        "Теперь выберите культуру.",
        reply_markup=get_crop_categories_keyboard(),
    )


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is None:
        return
    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    field_status = (
        f"Поле: {user.latitude:.5f}, {user.longitude:.5f}"
        if user.latitude is not None and user.longitude is not None
        else "Поле ещё не задано"
    )
    await message.answer(
        "🌾 <b>Агрометеорологический бот</b>\n\n"
        f"{field_status}\n"
        f"Культура: {get_crop_name(user.selected_crop or 'wheat')}\n\n"
        "Основной сценарий: поле → культура → отчёт.\n"
        "Справка: /help",
        reply_markup=get_main_keyboard(),
    )


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(_HELP_TEXT, reply_markup=get_main_keyboard())


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Текущий ввод отменён.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=get_main_keyboard())


@router.callback_query(F.data == "menu")
async def menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "Выберите действие:",
        reply_markup=get_main_keyboard(),
    )


@router.callback_query(F.data == "my_field")
async def show_field(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    user = await get_user(session, callback.from_user.id)
    if user and user.latitude is not None and user.longitude is not None:
        text = (
            "📍 <b>Текущее поле</b>\n"
            f"Широта: {user.latitude:.5f}\n"
            f"Долгота: {user.longitude:.5f}"
        )
    else:
        text = "📍 Поле ещё не задано."
    await callback.message.edit_text(text, reply_markup=get_field_keyboard())


@router.callback_query(F.data == "field_location")
async def request_location(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(FieldStates.waiting_for_coordinates)
    await callback.message.answer(
        "Нажмите кнопку ниже и отправьте геолокацию поля.",
        reply_markup=get_location_reply_keyboard(),
    )


@router.callback_query(F.data == "field_manual")
async def request_manual_coordinates(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(FieldStates.waiting_for_coordinates)
    await callback.message.answer(
        "Введите широту и долготу в десятичных градусах.\n"
        "Пример: <code>55.7558, 37.6173</code>",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(F.location)
async def receive_location(message: Message, session: AsyncSession, state: FSMContext) -> None:
    coords = Coordinates(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
    )
    await _save_field(message, session, coords)
    await state.clear()


@router.message(FieldStates.waiting_for_coordinates, F.text.casefold() == "отмена")
async def cancel_field_input(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Ввод координат отменён.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(FieldStates.waiting_for_coordinates, F.text)
async def receive_manual_coordinates(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    try:
        coords = parse_coordinates(message.text or "")
    except ValueError as exc:
        await message.answer(f"❌ {exc}")
        return
    await _save_field(message, session, coords)
    await state.clear()


@router.callback_query(F.data == "crop_choose")
async def choose_crop(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_text(
        "🌱 Выберите категорию культуры:",
        reply_markup=get_crop_categories_keyboard(),
    )


@router.callback_query(F.data.startswith("crop_cat:"))
async def choose_crop_category(callback: CallbackQuery) -> None:
    await callback.answer()
    category_id = callback.data.split(":", 1)[1]
    await callback.message.edit_text(
        "Выберите культуру:",
        reply_markup=get_crop_list_keyboard(category_id),
    )


@router.callback_query(F.data.startswith("crop_pick:"))
async def save_crop(callback: CallbackQuery, session: AsyncSession) -> None:
    crop_key = callback.data.split(":", 1)[1]
    if crop_key not in CROPS:
        await callback.answer("Неизвестная культура", show_alert=True)
        return
    await update_user_crop(session, callback.from_user.id, crop_key)
    await callback.answer("Культура сохранена")
    await callback.message.edit_text(
        f"✅ Выбрано: <b>{get_crop_name(crop_key)}</b>\n"
        "Можно сформировать агроотчёт.",
        reply_markup=get_main_keyboard(),
    )


@router.callback_query(F.data == "agro_report")
async def agro_report(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    user = await get_user(session, callback.from_user.id)
    if user is None or user.latitude is None or user.longitude is None:
        await callback.message.edit_text(
            "Сначала задайте координаты поля.",
            reply_markup=get_field_keyboard(),
        )
        return

    progress = await callback.message.answer("🌐 Получаю оперативные данные…")
    try:
        report = await generate_agro_report(
            user.latitude,
            user.longitude,
            user.selected_crop or "wheat",
        )
        await progress.edit_text(report.text, reply_markup=get_main_keyboard())
    except OpenMeteoError:
        logger.warning("Open-Meteo unavailable for user %s", callback.from_user.id)
        await progress.edit_text(
            "⚠️ Оперативные метеоданные сейчас недоступны. "
            "Упрощённая эвристика не подменяет расчёт; повторите запрос позже.",
            reply_markup=get_main_keyboard(),
        )
    except Exception:
        logger.exception("Agro report failed for user %s", callback.from_user.id)
        await progress.edit_text(
            "Не удалось сформировать отчёт из-за внутренней ошибки.",
            reply_markup=get_main_keyboard(),
        )


@router.callback_query(F.data == "settings")
async def settings(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    user = await get_or_create_user(session, callback.from_user.id)
    enabled = bool(user.daily_digest)
    await callback.message.edit_text(
        "⚙️ <b>Уведомления</b>\n"
        f"Ежедневный отчёт: {'включён' if enabled else 'выключен'}",
        reply_markup=get_settings_keyboard(enabled),
    )


@router.callback_query(F.data == "toggle_digest")
async def toggle_digest(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_or_create_user(session, callback.from_user.id)
    enabled = not bool(user.daily_digest)
    user = await set_daily_digest(session, callback.from_user.id, enabled)
    await callback.answer("Настройка сохранена")
    await callback.message.edit_text(
        "⚙️ <b>Уведомления</b>\n"
        f"Ежедневный отчёт: {'включён' if user.daily_digest else 'выключен'}",
        reply_markup=get_settings_keyboard(bool(user.daily_digest)),
    )
