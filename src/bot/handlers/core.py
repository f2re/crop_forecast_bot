from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from src.agro.crop_catalog import CROPS, get_crop, get_crop_name
from src.api.open_meteo import OpenMeteoError
from src.application.agro_report import generate_agro_report
from src.bot.keyboards import (
    get_crop_categories_keyboard,
    get_crop_list_keyboard,
    get_field_actions_keyboard,
    get_field_keyboard,
    get_fields_keyboard,
    get_location_reply_keyboard,
    get_main_keyboard,
    get_new_field_coordinate_keyboard,
    get_phase_keyboard,
    get_season_keyboard,
    get_settings_keyboard,
)
from src.database.crud import (
    FieldSummary,
    activate_field,
    clear_manual_phase,
    create_field,
    get_field_context,
    get_field_summary,
    get_or_create_user,
    list_fields,
    rename_field,
    save_coordinates,
    set_field_notifications,
    set_manual_phase,
    set_season_start as save_season_start,
    update_field_coordinates,
    update_field_metadata,
    update_user_crop,
)
from src.domain.coordinates import Coordinates, parse_coordinates
from src.domain.fields import normalize_field_name
from src.domain.season import local_today, parse_season_date

logger = logging.getLogger(__name__)
router = Router(name="core")

_HELP_TEXT = (
    "🆘 <b>Как пользоваться ботом</b>\n\n"
    "1️⃣ Откройте «Мои поля». Создайте поле или выберите существующее.\n"
    "2️⃣ Для активного поля выберите культуру.\n"
    "3️⃣ В разделе «Сезон и фаза» укажите дату посева и, при наличии, "
    "фактическую фазу.\n"
    "4️⃣ Нажмите «Агроотчёт».\n\n"
    "У каждого поля свои координаты, сезон и настройки уведомлений. "
    "Отчёты и алерты формируются только для активного поля.\n\n"
    "Дата сезона нужна для накопленных ГДД. Фаза не угадывается автоматически: "
    "её можно указать по наблюдению на поле.\n\n"
    "<b>Команды</b>\n"
    "/start — главное меню\n"
    "/help — эта справка\n"
    "/cancel — отменить текущий ввод"
)


class FieldStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_rename = State()
    waiting_for_coordinates = State()


class SeasonStates(StatesGroup):
    waiting_for_start_date = State()


def _field_details(field: FieldSummary) -> str:
    active = "✅ Активное поле" if field.is_active else "▫️ Неактивное поле"
    season = (
        field.season_start_date.strftime("%d.%m.%Y")
        if field.season_start_date
        else "не задан"
    )
    phase = html.escape(field.phenological_phase) if field.phenological_phase else "не указана"
    elevation = (
        f"{field.elevation_m:.0f} м"
        if field.elevation_m is not None
        else "будет определена после отчёта"
    )
    timezone_source = html.escape(field.timezone_source or "не указан")
    elevation_source = html.escape(field.elevation_source or "не указан")
    return (
        f"🗺 <b>{html.escape(field.field_name)}</b>\n"
        f"{active}\n"
        f"📍 {field.latitude:.5f}, {field.longitude:.5f}\n"
        f"🕒 {field.timezone} · источник: {timezone_source}\n"
        f"🏔 {elevation} · источник: {elevation_source}\n"
        f"🌱 {get_crop_name(field.crop_key)}\n"
        f"📅 Сезон: {season}\n"
        f"🌿 Фаза: {phase}\n"
        f"📨 Ежедневный отчёт: {'включён' if field.daily_digest_enabled else 'выключен'}\n"
        f"🌡 Температурные алерты: {'включены' if field.frost_alerts_enabled else 'выключены'}"
    )


def _season_text(context) -> str:
    start = (
        context.season_start_date.strftime("%d.%m.%Y")
        if context.season_start_date
        else "не задана"
    )
    phase = html.escape(context.phenological_phase) if context.phenological_phase else "не указана"
    phase_note = " (по наблюдению пользователя)" if context.phase_source == "user" else ""
    return (
        "📅 <b>Активный сезон</b>\n"
        f"🗺 Поле: {html.escape(context.field_name)}\n"
        f"🌱 Культура: {get_crop_name(context.crop_key)}\n"
        f"📆 Дата посева/начала: {start}\n"
        f"🌿 Фаза: {phase}{phase_note}\n"
        f"🕒 Часовой пояс: {context.timezone}\n\n"
        "ГДД считаются с даты сезона только при полном покрытии ряда. "
        "Автоматическая фенофаза не выводится без валидированной модели."
    )


async def _show_fields(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    fields = await list_fields(session, callback.from_user.id)
    await callback.answer()
    if not fields:
        await callback.message.edit_text(
            "🗺 <b>Поля ещё не добавлены.</b>\n\n"
            "Добавьте первое поле геолокацией или координатами.",
            reply_markup=get_field_keyboard(),
        )
        return
    await callback.message.edit_text(
        "🗺 <b>Мои поля</b>\n\n"
        "✅ — активное поле. Отчёт, сезон и уведомления относятся к нему.\n"
        "Нажмите поле для просмотра или переключения.",
        reply_markup=get_fields_keyboard(fields),
    )


async def _save_coordinates_for_action(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    coords: Coordinates,
) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    action = data.get("field_action", "initial")

    try:
        if action == "create":
            field_name = normalize_field_name(str(data.get("field_name", "")))
            field = await create_field(
                session,
                message.from_user.id,
                name=field_name,
                latitude=coords.latitude,
                longitude=coords.longitude,
            )
            await state.clear()
            await message.answer(
                f"✅ Поле <b>{html.escape(field.field_name)}</b> создано и стало активным.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await message.answer(
                "Теперь выберите культуру для нового поля.",
                reply_markup=get_crop_categories_keyboard(),
            )
            return

        if action == "update":
            field_id = int(data["field_id"])
            field = await update_field_coordinates(
                session,
                message.from_user.id,
                field_id,
                latitude=coords.latitude,
                longitude=coords.longitude,
            )
            await state.clear()
            await message.answer(
                "✅ Координаты поля обновлены. Часовой пояс и высота будут "
                "обновлены при следующем агроотчёте.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await message.answer(
                _field_details(field),
                reply_markup=get_field_actions_keyboard(
                    field.field_id,
                    is_active=field.is_active,
                ),
            )
            return

        existing = await list_fields(session, message.from_user.id)
        await save_coordinates(
            session,
            telegram_id=message.from_user.id,
            latitude=coords.latitude,
            longitude=coords.longitude,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        await state.clear()
        context = await get_field_context(session, message.from_user.id)
        if context is None:
            raise RuntimeError("Поле не найдено после сохранения координат.")
        await message.answer(
            f"✅ Координаты сохранены для поля "
            f"<b>{html.escape(context.field_name)}</b>: "
            f"{coords.latitude:.5f}, {coords.longitude:.5f}",
            reply_markup=ReplyKeyboardRemove(),
        )
        if not existing:
            await message.answer(
                "Теперь выберите культуру.",
                reply_markup=get_crop_categories_keyboard(),
            )
        else:
            field = await get_field_summary(session, message.from_user.id, context.field_id)
            await message.answer(
                _field_details(field),
                reply_markup=get_field_actions_keyboard(
                    field.field_id,
                    is_active=field.is_active,
                ),
            )
    except (ValueError, KeyError) as exc:
        logger.info("Field input rejected for user %s: %s", message.from_user.id, exc)
        await message.answer(f"❌ {exc}")


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
    fields = await list_fields(session, user.telegram_id)
    context = await get_field_context(session, user.telegram_id)
    if context is None:
        profile = "🗺 Поля ещё не заданы\n🌱 Культура: не выбрана\n📅 Сезон: не задан"
    else:
        season_label = (
            context.season_start_date.strftime("%d.%m.%Y")
            if context.season_start_date
            else "не задан"
        )
        profile = (
            f"🗺 Активное поле: {html.escape(context.field_name)}\n"
            f"📍 {context.latitude:.5f}, {context.longitude:.5f}\n"
            f"🌱 Культура: {get_crop_name(context.crop_key)}\n"
            f"📅 Сезон: {season_label}\n"
            f"📚 Всего полей: {len(fields)}"
        )
    await message.answer(
        "🌾 <b>Агрометеорологический бот</b>\n\n"
        f"{profile}\n\n"
        "Основной сценарий: поле → культура → сезон → отчёт.\n"
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
    await callback.message.edit_text("Выберите действие:", reply_markup=get_main_keyboard())


@router.callback_query(F.data == "fields")
@router.callback_query(F.data == "my_field")
async def show_fields(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await _show_fields(callback, session, state)


@router.callback_query(F.data.startswith("field_open:"))
async def open_field(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        field_id = int(callback.data.split(":", 1)[1])
        field = await get_field_summary(session, callback.from_user.id, field_id)
    except (ValueError, IndexError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        _field_details(field),
        reply_markup=get_field_actions_keyboard(field.field_id, is_active=field.is_active),
    )


@router.callback_query(F.data == "field_add")
async def request_field_name(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(FieldStates.waiting_for_name)
    await callback.answer()
    await callback.message.answer(
        "➕ <b>Новое поле</b>\n\n"
        "Введите короткое понятное название, например:\n"
        "<code>Северное</code> или <code>Поле 12</code>.\n\n"
        "Для отмены отправьте /cancel.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(FieldStates.waiting_for_name, F.text)
async def receive_field_name(message: Message, state: FSMContext) -> None:
    try:
        field_name = normalize_field_name(message.text or "")
    except ValueError as exc:
        await message.answer(f"❌ {exc}")
        return
    await state.update_data(field_action="create", field_name=field_name)
    await state.set_state(FieldStates.waiting_for_coordinates)
    await message.answer(
        f"Название: <b>{html.escape(field_name)}</b>\n"
        "Теперь задайте координаты поля.",
        reply_markup=get_new_field_coordinate_keyboard(),
    )


@router.callback_query(F.data == "field_create_location")
async def request_new_field_location(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("field_action") != "create" or not data.get("field_name"):
        await callback.answer("Сначала введите название поля", show_alert=True)
        return
    await state.set_state(FieldStates.waiting_for_coordinates)
    await callback.answer()
    await callback.message.answer(
        "Отправьте геолокацию нового поля.",
        reply_markup=get_location_reply_keyboard(),
    )


@router.callback_query(F.data == "field_create_manual")
async def request_new_field_coordinates(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("field_action") != "create" or not data.get("field_name"):
        await callback.answer("Сначала введите название поля", show_alert=True)
        return
    await state.set_state(FieldStates.waiting_for_coordinates)
    await callback.answer()
    await callback.message.answer(
        "Введите координаты нового поля.\n"
        "Пример: <code>55.7558, 37.6173</code>",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.callback_query(F.data.startswith("field_rename:"))
async def request_field_rename(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        field_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный идентификатор поля", show_alert=True)
        return
    await state.clear()
    await state.update_data(field_id=field_id)
    await state.set_state(FieldStates.waiting_for_rename)
    await callback.answer()
    await callback.message.answer(
        "✏️ Введите новое название поля. Для отмены отправьте /cancel.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(FieldStates.waiting_for_rename, F.text)
async def receive_field_rename(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    try:
        field_id = int(data["field_id"])
        field_name = normalize_field_name(message.text or "")
        field = await rename_field(
            session,
            message.from_user.id,
            field_id,
            field_name,
        )
    except (ValueError, KeyError) as exc:
        await message.answer(f"❌ {exc}")
        return
    await state.clear()
    await message.answer(
        "✅ Поле переименовано.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        _field_details(field),
        reply_markup=get_field_actions_keyboard(field.field_id, is_active=field.is_active),
    )


@router.callback_query(F.data.startswith("field_activate:"))
async def switch_active_field(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        field_id = int(callback.data.split(":", 1)[1])
        field = await activate_field(session, callback.from_user.id, field_id)
    except (ValueError, IndexError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Активное поле изменено")
    await callback.message.edit_text(
        f"✅ Активное поле: <b>{html.escape(field.field_name)}</b>\n\n"
        "Культура, сезон, фаза и уведомления переключены вместе с полем.",
        reply_markup=get_field_actions_keyboard(field.field_id, is_active=True),
    )


@router.callback_query(F.data.startswith("field_update_location:"))
async def request_field_location_update(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    try:
        field_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный идентификатор поля", show_alert=True)
        return
    await state.clear()
    await state.update_data(field_action="update", field_id=field_id)
    await state.set_state(FieldStates.waiting_for_coordinates)
    await callback.answer()
    await callback.message.answer(
        "Отправьте новую геолокацию поля.",
        reply_markup=get_location_reply_keyboard(),
    )


@router.callback_query(F.data.startswith("field_update_manual:"))
async def request_field_coordinates_update(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    try:
        field_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный идентификатор поля", show_alert=True)
        return
    await state.clear()
    await state.update_data(field_action="update", field_id=field_id)
    await state.set_state(FieldStates.waiting_for_coordinates)
    await callback.answer()
    await callback.message.answer(
        "Введите новые координаты.\n"
        "Пример: <code>55.7558, 37.6173</code>",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.callback_query(F.data == "field_location")
async def request_location(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(field_action="initial")
    await state.set_state(FieldStates.waiting_for_coordinates)
    await callback.answer()
    await callback.message.answer(
        "Нажмите кнопку ниже и отправьте геолокацию поля.",
        reply_markup=get_location_reply_keyboard(),
    )


@router.callback_query(F.data == "field_manual")
async def request_manual_coordinates(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(field_action="initial")
    await state.set_state(FieldStates.waiting_for_coordinates)
    await callback.answer()
    await callback.message.answer(
        "Введите широту и долготу в десятичных градусах.\n"
        "Пример: <code>55.7558, 37.6173</code>",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(FieldStates.waiting_for_coordinates, F.text.casefold() == "отмена")
async def cancel_field_input(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ввод координат отменён.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=get_main_keyboard())


@router.message(F.location)
async def receive_location(message: Message, session: AsyncSession, state: FSMContext) -> None:
    coords = Coordinates(
        latitude=message.location.latitude,
        longitude=message.location.longitude,
    )
    await _save_coordinates_for_action(message, session, state, coords)


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
    await _save_coordinates_for_action(message, session, state, coords)


@router.callback_query(F.data == "crop_choose")
async def choose_crop(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        f"🌱 Культура для поля <b>{html.escape(context.field_name)}</b>\n\n"
        "Выберите категорию:",
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
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    await update_user_crop(session, callback.from_user.id, crop_key)
    context = await get_field_context(session, callback.from_user.id)
    await callback.answer("Культура сохранена")
    await callback.message.edit_text(
        f"✅ Для поля <b>{html.escape(context.field_name)}</b> выбрано: "
        f"<b>{get_crop_name(crop_key)}</b>\n"
        "Укажите дату посева/начала активного сезона.",
        reply_markup=get_season_keyboard(
            has_start=context.season_start_date is not None,
            has_phase=context.phenological_phase is not None,
        ),
    )


@router.callback_query(F.data == "season")
async def show_season(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.message.edit_text(
            "Сначала добавьте поле.",
            reply_markup=get_field_keyboard(),
        )
        return
    await callback.message.edit_text(
        _season_text(context),
        reply_markup=get_season_keyboard(
            has_start=context.season_start_date is not None,
            has_phase=context.phenological_phase is not None,
        ),
    )


@router.callback_query(F.data == "season_start_set")
async def request_season_start(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    await callback.answer()
    await state.set_state(SeasonStates.waiting_for_start_date)
    await callback.message.answer(
        f"📅 Поле: <b>{html.escape(context.field_name)}</b>\n"
        "Введите дату посева или начала активного сезона.\n"
        "Формат: <code>ДД.ММ.ГГГГ</code> или <code>ГГГГ-ММ-ДД</code>.\n\n"
        "Пример: <code>15.04.2026</code>\n"
        "Для озимой культуры можно указать дату прошлого календарного года.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(SeasonStates.waiting_for_start_date, F.text.casefold() == "отмена")
async def cancel_season_input(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ввод даты отменён.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=get_main_keyboard())


@router.message(SeasonStates.waiting_for_start_date, F.text)
async def receive_season_start(
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
        await save_season_start(session, message.from_user.id, value)
    except ValueError as exc:
        await message.answer(f"❌ {exc}")
        return
    await state.clear()
    await message.answer(
        f"✅ Для поля <b>{html.escape(context.field_name)}</b> дата сезона: "
        f"<b>{value:%d.%m.%Y}</b>\n"
        "Следующий отчёт попробует достроить ряд реанализом до этой даты. "
        "При неполном покрытии это будет явно указано.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Можно сформировать отчёт.", reply_markup=get_main_keyboard())


@router.callback_query(F.data == "season_phase")
async def choose_phase(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        f"🌿 Поле: <b>{html.escape(context.field_name)}</b>\n"
        "Выберите фактически наблюдаемую фазу.\n"
        "Бот сохранит её как пользовательское наблюдение, а не результат модели.",
        reply_markup=get_phase_keyboard(context.crop_key),
    )


@router.callback_query(F.data.startswith("phase_pick:"))
async def save_phase(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    phases = list(get_crop(context.crop_key).get("gdd_stages", {}).keys())
    try:
        index = int(callback.data.split(":", 1)[1])
        phase = phases[index]
    except (ValueError, IndexError):
        await callback.answer("Неизвестная фаза", show_alert=True)
        return
    await set_manual_phase(session, callback.from_user.id, phase)
    await callback.answer("Фаза сохранена")
    await callback.message.edit_text(
        f"✅ Поле <b>{html.escape(context.field_name)}</b>: фактическая фаза "
        f"<b>{phase}</b>\n"
        "Она будет показана как наблюдение пользователя, без пересчёта порога повреждения.",
        reply_markup=get_main_keyboard(),
    )


@router.callback_query(F.data == "phase_clear")
async def clear_phase(callback: CallbackQuery, session: AsyncSession) -> None:
    await clear_manual_phase(session, callback.from_user.id)
    await callback.answer("Фаза удалена")
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.message.edit_text("Поле не найдено.", reply_markup=get_main_keyboard())
        return
    await callback.message.edit_text(
        _season_text(context),
        reply_markup=get_season_keyboard(
            has_start=context.season_start_date is not None,
            has_phase=False,
        ),
    )


@router.callback_query(F.data == "agro_report")
async def agro_report(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.message.edit_text(
            "Сначала добавьте поле.",
            reply_markup=get_field_keyboard(),
        )
        return

    await session.rollback()
    progress = await callback.message.answer(
        f"🌐 Поле <b>{html.escape(context.field_name)}</b>: "
        "получаю прогноз и проверяю ряд сезона…"
    )
    try:
        report = await generate_agro_report(
            context.latitude,
            context.longitude,
            context.crop_key,
            season_start_date=context.season_start_date,
            phenological_phase=context.phenological_phase,
            field_name=context.field_name,
        )
        await update_field_metadata(
            session,
            context.field_id,
            timezone=report.timezone,
            timezone_source=report.metadata_source,
            elevation_m=report.elevation_m,
            elevation_source=report.metadata_source,
        )
        await progress.edit_text(report.text, reply_markup=get_main_keyboard())
    except OpenMeteoError:
        logger.warning(
            "Open-Meteo unavailable for user %s field %s",
            callback.from_user.id,
            context.field_id,
        )
        await progress.edit_text(
            "⚠️ Оперативные метеоданные сейчас недоступны. "
            "Упрощённая эвристика не подменяет расчёт; повторите запрос позже.",
            reply_markup=get_main_keyboard(),
        )
    except Exception:
        logger.exception(
            "Agro report failed for user %s field %s",
            callback.from_user.id,
            context.field_id,
        )
        await progress.edit_text(
            "Не удалось сформировать отчёт из-за внутренней ошибки.",
            reply_markup=get_main_keyboard(),
        )


async def _show_settings(callback: CallbackQuery, context) -> None:
    await callback.message.edit_text(
        "⚙️ <b>Уведомления активного поля</b>\n"
        f"🗺 {html.escape(context.field_name)}\n"
        f"📨 Ежедневный отчёт: {'включён' if context.daily_digest else 'выключен'}\n"
        f"🌡 Температурные алерты: {'включены' if context.frost_alerts else 'выключены'}",
        reply_markup=get_settings_keyboard(
            daily_digest_enabled=context.daily_digest,
            frost_alerts_enabled=context.frost_alerts,
        ),
    )


@router.callback_query(F.data == "settings")
async def settings(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.message.edit_text(
            "Сначала добавьте поле.",
            reply_markup=get_field_keyboard(),
        )
        return
    await _show_settings(callback, context)


@router.callback_query(F.data == "toggle_digest")
async def toggle_digest(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    context = await set_field_notifications(
        session,
        callback.from_user.id,
        daily_digest=not context.daily_digest,
    )
    await callback.answer("Настройка сохранена")
    await _show_settings(callback, context)


@router.callback_query(F.data == "toggle_frost")
async def toggle_frost(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    context = await set_field_notifications(
        session,
        callback.from_user.id,
        frost_alerts=not context.frost_alerts,
    )
    await callback.answer("Настройка сохранена")
    await _show_settings(callback, context)
