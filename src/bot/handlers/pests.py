from __future__ import annotations

import html
import logging
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.open_meteo import OpenMeteoError
from src.application.pest_monitoring import (
    PestMonitorRequest,
    evaluate_pest_monitors,
)
from src.bot.keyboards import get_field_keyboard, get_main_keyboard
from src.bot.pest_calendar import (
    build_pest_calendar,
    parse_pest_calendar_date,
    parse_pest_calendar_month,
    validate_biofix_date,
)
from src.bot.pest_keyboards import (
    get_pest_help_keyboard,
    get_pest_models_keyboard,
    get_pest_monitor_keyboard,
    get_pest_unavailable_keyboard,
)
from src.bot.pest_messages import (
    format_pest_help,
    format_pest_model_intro,
    format_pest_outlook,
    format_pest_overview,
)
from src.bot.telegram_text import answer_html, edit_html
from src.database.pest_monitoring import (
    ActivePestContext,
    disable_pest_monitor,
    get_active_pest_context,
    upsert_pest_monitor,
)
from src.domain.pests import (
    PestModel,
    get_pest_model,
    supported_pests_for_crop,
    validate_pest_for_crop,
)
from src.domain.season import local_today, parse_season_date

logger = logging.getLogger(__name__)
router = Router(name="pests")


class PestStates(StatesGroup):
    choosing_biofix = State()
    waiting_for_manual_biofix = State()


async def _base_context(
    session: AsyncSession,
    telegram_id: int,
) -> ActivePestContext | None:
    return await get_active_pest_context(session, telegram_id)


async def _configured_context(
    session: AsyncSession,
    telegram_id: int,
    pest_key: str,
) -> ActivePestContext | None:
    return await get_active_pest_context(session, telegram_id, pest_key)


async def _active_model_key(
    session: AsyncSession,
    telegram_id: int,
    models: tuple[PestModel, ...],
) -> str | None:
    for model in models:
        context = await _configured_context(session, telegram_id, model.key)
        if context is not None and context.monitor_id is not None and context.enabled:
            return model.key
    return None


async def _overview_text_and_keyboard(
    session: AsyncSession,
    telegram_id: int,
):
    context = await _base_context(session, telegram_id)
    if context is None:
        return (
            "Сначала добавьте поле и выберите культуру.",
            get_field_keyboard(),
        )
    models = supported_pests_for_crop(context.crop_key)
    active_key = await _active_model_key(session, telegram_id, models)
    text = format_pest_overview(
        field_name=context.field_name,
        crop_key=context.crop_key,
        models=models,
        active_pest_key=active_key,
    )
    keyboard = (
        get_pest_models_keyboard(models, active_pest_key=active_key)
        if models
        else get_pest_unavailable_keyboard()
    )
    return text, keyboard


async def _evaluate_context(context: ActivePestContext):
    if context.monitor_id is None or context.pest_key is None:
        raise ValueError("Сначала укажите первую находку вредителя.")
    if context.biofix_date is None:
        raise ValueError("Не указана дата первой находки вредителя.")
    results = await evaluate_pest_monitors(
        context.latitude,
        context.longitude,
        (
            PestMonitorRequest(
                monitor_id=context.monitor_id,
                pest_key=context.pest_key,
                biofix_date=context.biofix_date,
            ),
        ),
    )
    return results[0]


async def _show_model(
    message: Message,
    session: AsyncSession,
    telegram_id: int,
    model: PestModel,
) -> None:
    context = await _configured_context(session, telegram_id, model.key)
    if context is None:
        await edit_html(
            message,
            "Сначала добавьте поле и выберите культуру.",
            reply_markup=get_field_keyboard(),
        )
        return
    try:
        validate_pest_for_crop(model.key, context.crop_key)
    except ValueError as exc:
        await edit_html(
            message,
            f"⚠️ {html.escape(str(exc))}",
            reply_markup=get_pest_unavailable_keyboard(),
        )
        return

    configured = context.monitor_id is not None
    if not configured or not context.enabled:
        await edit_html(
            message,
            format_pest_model_intro(
                model,
                field_name=context.field_name,
                crop_key=context.crop_key,
                configured=configured,
                enabled=context.enabled,
                biofix_date=context.biofix_date,
            ),
            reply_markup=get_pest_monitor_keyboard(
                model,
                configured=configured,
                enabled=context.enabled,
            ),
        )
        return

    try:
        result = await _evaluate_context(context)
    except OpenMeteoError:
        logger.warning(
            "Pest weather data unavailable for user %s field %s pest %s",
            telegram_id,
            context.field_id,
            model.key,
        )
        await edit_html(
            message,
            "⚠️ Температурный ряд сейчас недоступен. Настройка сохранена; "
            "бот повторит расчёт позже и не заменит пропуск догадкой.",
            reply_markup=get_pest_monitor_keyboard(
                model,
                configured=True,
                enabled=True,
            ),
        )
        return

    await edit_html(
        message,
        format_pest_outlook(
            result.outlook,
            field_name=context.field_name,
            crop_key=context.crop_key,
            source=result.source,
        ),
        reply_markup=get_pest_monitor_keyboard(
            model,
            configured=True,
            enabled=True,
        ),
    )


@router.message(Command("pests"))
async def pest_command(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return
    await state.clear()
    text, keyboard = await _overview_text_and_keyboard(
        session,
        message.from_user.id,
    )
    await answer_html(message, text, reply_markup=keyboard)


@router.callback_query(F.data == "pest_overview")
async def pest_overview(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is None:
        return
    text, keyboard = await _overview_text_and_keyboard(
        session,
        callback.from_user.id,
    )
    await edit_html(callback.message, text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("pest_select:"))
@router.callback_query(F.data.startswith("pest_refresh:"))
async def select_or_refresh_pest(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    pest_key = (callback.data or "").partition(":")[2]
    try:
        model = get_pest_model(pest_key)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await _show_model(
            callback.message,
            session,
            callback.from_user.id,
            model,
        )


@router.callback_query(F.data.startswith("pest_setup:"))
async def open_pest_calendar(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    pest_key = (callback.data or "").partition(":")[2]
    try:
        model = get_pest_model(pest_key)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    context = await _configured_context(session, callback.from_user.id, pest_key)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    try:
        validate_pest_for_crop(model.key, context.crop_key)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    today = local_today(context.timezone)
    selected = context.biofix_date
    display = selected or today
    await state.clear()
    await state.set_state(PestStates.choosing_biofix)
    await state.update_data(pest_key=pest_key)
    await callback.answer()
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        f"📅 <b>{html.escape(model.biofix_label.capitalize())}</b>\n"
        f"Поле: {html.escape(context.field_name)}\n\n"
        "Выберите дату реальной находки. Дата нужна как точка отсчёта; "
        "погода до неё в развитие вредителя не включается.",
        reply_markup=build_pest_calendar(
            display,
            today=today,
            selected=selected,
        ),
    )


@router.callback_query(F.data == "pest_calendar:noop")
async def pest_calendar_noop(callback: CallbackQuery) -> None:
    await callback.answer()


async def _pending_model(state: FSMContext) -> PestModel:
    data = await state.get_data()
    pest_key = str(data.get("pest_key", ""))
    if not pest_key:
        raise ValueError("Выбор вредителя устарел. Откройте раздел заново.")
    return get_pest_model(pest_key)


@router.callback_query(F.data.startswith("pest_calendar:nav:"))
async def navigate_pest_calendar(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    try:
        model = await _pending_model(state)
        display = parse_pest_calendar_month(callback.data or "")
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    context = await _configured_context(session, callback.from_user.id, model.key)
    if context is None:
        await callback.answer("Поле не найдено", show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(
            reply_markup=build_pest_calendar(
                display,
                today=local_today(context.timezone),
                selected=context.biofix_date,
            )
        )


async def _save_biofix(
    session: AsyncSession,
    telegram_id: int,
    state: FSMContext,
    value: date,
) -> tuple[PestModel, ActivePestContext]:
    model = await _pending_model(state)
    context = await _configured_context(session, telegram_id, model.key)
    if context is None:
        raise ValueError("Сначала добавьте поле и выберите культуру.")
    validated = validate_biofix_date(
        value,
        today=local_today(context.timezone),
    )
    saved = await upsert_pest_monitor(
        session,
        telegram_id,
        pest_key=model.key,
        biofix_date=validated,
    )
    await state.clear()
    return model, saved


@router.callback_query(F.data.startswith("pest_calendar:pick:"))
async def pick_pest_biofix(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    try:
        value = parse_pest_calendar_date(callback.data or "")
        model, _ = await _save_biofix(
            session,
            callback.from_user.id,
            state,
            value,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Наблюдение включено")
    if callback.message is not None:
        await _show_model(
            callback.message,
            session,
            callback.from_user.id,
            model,
        )


@router.callback_query(F.data == "pest_calendar:manual")
async def request_manual_pest_biofix(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    try:
        await _pending_model(state)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.set_state(PestStates.waiting_for_manual_biofix)
    await callback.answer()
    if callback.message is not None:
        await answer_html(
            callback.message,
            "⌨️ Введите дату первой находки: <code>ДД.ММ.ГГГГ</code> "
            "или <code>ГГГГ-ММ-ДД</code>.\nДля отмены отправьте /cancel.",
        )


@router.message(PestStates.waiting_for_manual_biofix, Command("cancel"))
@router.message(
    PestStates.waiting_for_manual_biofix,
    F.text.casefold() == "отмена",
)
async def cancel_manual_pest_biofix(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer("Ввод даты отменён.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=get_main_keyboard())


@router.message(PestStates.waiting_for_manual_biofix, F.text)
async def receive_manual_pest_biofix(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return
    try:
        model = await _pending_model(state)
        context = await _configured_context(
            session,
            message.from_user.id,
            model.key,
        )
        if context is None:
            raise ValueError("Сначала добавьте поле и выберите культуру.")
        value = parse_season_date(
            message.text or "",
            today=local_today(context.timezone),
        )
        _, saved = await _save_biofix(
            session,
            message.from_user.id,
            state,
            value,
        )
    except ValueError as exc:
        await message.answer(f"❌ {exc}")
        return

    await message.answer(
        f"✅ Наблюдение включено с {saved.biofix_date:%d.%m.%Y}.",
        reply_markup=ReplyKeyboardRemove(),
    )
    try:
        result = await _evaluate_context(saved)
    except OpenMeteoError:
        await message.answer(
            "Настройка сохранена. Температурный ряд сейчас недоступен; "
            "бот повторит расчёт позже.",
            reply_markup=get_main_keyboard(),
        )
        return
    await answer_html(
        message,
        format_pest_outlook(
            result.outlook,
            field_name=saved.field_name,
            crop_key=saved.crop_key,
            source=result.source,
        ),
        reply_markup=get_pest_monitor_keyboard(
            model,
            configured=True,
            enabled=True,
        ),
    )


@router.callback_query(F.data.startswith("pest_disable:"))
async def disable_pest(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    pest_key = (callback.data or "").partition(":")[2]
    try:
        model = get_pest_model(pest_key)
        saved = await disable_pest_monitor(
            session,
            callback.from_user.id,
            pest_key,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.clear()
    await callback.answer("Напоминания отключены")
    if callback.message is not None:
        await edit_html(
            callback.message,
            format_pest_model_intro(
                model,
                field_name=saved.field_name,
                crop_key=saved.crop_key,
                configured=True,
                enabled=False,
                biofix_date=saved.biofix_date,
            ),
            reply_markup=get_pest_monitor_keyboard(
                model,
                configured=True,
                enabled=False,
            ),
        )


@router.callback_query(F.data.startswith("pest_help:"))
async def pest_help(callback: CallbackQuery) -> None:
    pest_key = (callback.data or "").partition(":")[2]
    try:
        model = get_pest_model(pest_key)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await edit_html(
            callback.message,
            format_pest_help(model),
            reply_markup=get_pest_help_keyboard(model),
        )
