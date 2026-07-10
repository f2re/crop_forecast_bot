from __future__ import annotations

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
    get_field_keyboard,
    get_location_reply_keyboard,
    get_main_keyboard,
    get_phase_keyboard,
    get_season_keyboard,
    get_settings_keyboard,
)
from src.database.crud import (
    clear_manual_phase,
    get_field_context,
    get_or_create_user,
    save_coordinates,
    set_daily_digest,
    set_manual_phase,
    set_season_start as save_season_start,
    update_field_metadata,
    update_user_crop,
)
from src.domain.coordinates import Coordinates, parse_coordinates
from src.domain.season import local_today, parse_season_date

logger = logging.getLogger(__name__)
router = Router(name="core")

_HELP_TEXT = (
    "🆘 <b>Как пользоваться ботом</b>\n\n"
    "1️⃣ Откройте «Моё поле» и отправьте геолокацию или координаты.\n"
    "2️⃣ Выберите культуру.\n"
    "3️⃣ В разделе «Сезон и фаза» укажите дату посева и, при наличии, "
    "фактическую фазу.\n"
    "4️⃣ Нажмите «Агроотчёт».\n\n"
    "Дата сезона нужна для накопленных ГДД. Фаза не угадывается автоматически: "
    "её можно указать по наблюдению на поле.\n\n"
    "<b>Команды</b>\n"
    "/start — главное меню\n"
    "/help — эта справка\n"
    "/cancel — отменить текущий ввод"
)


class FieldStates(StatesGroup):
    waiting_for_coordinates = State()


class SeasonStates(StatesGroup):
    waiting_for_start_date = State()


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


def _season_text(context) -> str:
    start = (
        context.season_start_date.strftime("%d.%m.%Y")
        if context.season_start_date
        else "не задана"
    )
    phase = context.phenological_phase or "не указана"
    phase_note = " (по наблюдению пользователя)" if context.phase_source == "user" else ""
    return (
        "📅 <b>Активный сезон</b>\n"
        f"🗺 Поле: {context.field_name}\n"
        f"🌱 Культура: {get_crop_name(context.crop_key)}\n"
        f"📆 Дата посева/начала: {start}\n"
        f"🌿 Фаза: {phase}{phase_note}\n"
        f"🕒 Часовой пояс: {context.timezone}\n\n"
        "ГДД считаются с даты сезона только при полном покрытии ряда. "
        "Автоматическая фенофаза не выводится без валидированной модели."
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
    context = await get_field_context(session, user.telegram_id)
    if context is None:
        profile = "📍 Поле ещё не задано\n🌱 Культура: не выбрана\n📅 Сезон: не задан"
    else:
        season_label = (
            context.season_start_date.strftime("%d.%m.%Y")
            if context.season_start_date
            else "не задан"
        )
        profile = (
            f"📍 {context.field_name}: {context.latitude:.5f}, {context.longitude:.5f}\n"
            f"🌱 Культура: {get_crop_name(context.crop_key)}\n"
            f"📅 Сезон: {season_label}"
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


@router.callback_query(F.data == "my_field")
async def show_field(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    context = await get_field_context(session, callback.from_user.id)
    if context is not None:
        elevation = (
            f"\nВысота модели: {context.elevation_m:.0f} м"
            if context.elevation_m is not None
            else ""
        )
        text = (
            f"📍 <b>{context.field_name}</b>\n"
            f"Широта: {context.latitude:.5f}\n"
            f"Долгота: {context.longitude:.5f}\n"
            f"Часовой пояс: {context.timezone}{elevation}"
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
    await message.answer("Ввод координат отменён.", reply_markup=ReplyKeyboardRemove())


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
    context = await get_field_context(session, callback.from_user.id)
    await callback.answer("Культура сохранена")
    if context is None:
        await callback.message.edit_text(
            f"✅ Выбрано: <b>{get_crop_name(crop_key)}</b>\n"
            "Теперь задайте координаты поля.",
            reply_markup=get_field_keyboard(),
        )
        return
    await callback.message.edit_text(
        f"✅ Выбрано: <b>{get_crop_name(crop_key)}</b>\n"
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
            "Сначала задайте координаты поля.",
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
        await callback.answer("Сначала задайте поле", show_alert=True)
        return
    await callback.answer()
    await state.set_state(SeasonStates.waiting_for_start_date)
    await callback.message.answer(
        "📅 Введите дату посева или начала активного сезона.\n"
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
        await message.answer("Сначала задайте координаты поля.", reply_markup=get_field_keyboard())
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
        f"✅ Дата начала сезона сохранена: <b>{value:%d.%m.%Y}</b>\n"
        "Следующий отчёт попробует достроить ряд реанализом до этой даты. "
        "При неполном покрытии это будет явно указано.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Можно сформировать отчёт.", reply_markup=get_main_keyboard())


@router.callback_query(F.data == "season_phase")
async def choose_phase(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала задайте поле", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "🌿 Выберите фактически наблюдаемую фазу.\n"
        "Бот сохранит её как пользовательское наблюдение, а не результат модели.",
        reply_markup=get_phase_keyboard(context.crop_key),
    )


@router.callback_query(F.data.startswith("phase_pick:"))
async def save_phase(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала задайте поле", show_alert=True)
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
        f"✅ Фактическая фаза: <b>{phase}</b>\n"
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
            "Сначала задайте координаты поля.",
            reply_markup=get_field_keyboard(),
        )
        return

    # Release the read transaction before external weather I/O.
    await session.rollback()
    progress = await callback.message.answer("🌐 Получаю прогноз и проверяю ряд сезона…")
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
            elevation_m=report.elevation_m,
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
