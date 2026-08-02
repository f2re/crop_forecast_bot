from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.agro.crop_catalog import get_crop_name
from src.bot.keyboards import get_field_actions_keyboard, get_main_keyboard
from src.bot.telegram_text import answer_html, edit_html
from src.database.crops import FieldCropProfile, list_field_crops
from src.database.crud import (
    FieldSummary,
    get_field_context,
    get_field_summary,
    get_or_create_user,
    list_fields,
)

router = Router(name="profile")


def _crop_names(crops: tuple[FieldCropProfile, ...], fallback: str) -> str:
    keys = tuple(dict.fromkeys(item.crop_key for item in crops)) or (fallback,)
    return ", ".join(get_crop_name(key) for key in keys)


def _selected_crop(crops: tuple[FieldCropProfile, ...], fallback: str) -> str:
    selected = next((item.crop_key for item in crops if item.is_selected), fallback)
    return get_crop_name(selected)


def _field_text(
    field: FieldSummary,
    crops: tuple[FieldCropProfile, ...],
) -> str:
    active = "✅ Активное поле" if field.is_active else "▫️ Неактивное поле"
    season = (
        field.season_start_date.strftime("%d.%m.%Y")
        if field.season_start_date
        else "не задана"
    )
    phase = html.escape(field.phenological_phase) if field.phenological_phase else "не указана"
    elevation = (
        f"{field.elevation_m:.0f} м"
        if field.elevation_m is not None
        else "будет определена по данным провайдера"
    )
    names = html.escape(_crop_names(crops, field.crop_key))
    selected = html.escape(_selected_crop(crops, field.crop_key))
    return (
        f"🗺 <b>{html.escape(field.field_name)}</b>\n"
        f"{active}\n"
        f"📍 {field.latitude:.5f}, {field.longitude:.5f}\n"
        f"🕒 {html.escape(field.timezone)}\n"
        f"🏔 {elevation}\n"
        f"🌱 Культуры на точке: <b>{names}</b>\n"
        f"✅ Для отчёта выбрана: <b>{selected}</b>\n"
        f"📅 Посев/начало сезона выбранной культуры: {season}\n"
        f"🌿 Фаза выбранной культуры: {phase}\n"
        f"📨 Ежедневный отчёт: "
        f"{'включён' if field.daily_digest_enabled else 'выключен'}\n"
        f"⚠️ Погодные предупреждения: "
        f"{'включены' if field.frost_alerts_enabled else 'выключены'}"
    )


@router.message(CommandStart())
async def start(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
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
        profile = (
            "🗺 Поля ещё не заданы\n"
            "🌱 Культуры: не указаны\n"
            "📅 Сезон: не задан"
        )
    else:
        crops = await list_field_crops(
            session,
            user.telegram_id,
            field_id=context.field_id,
        )
        crop_names = html.escape(_crop_names(crops, context.crop_key))
        selected = html.escape(_selected_crop(crops, context.crop_key))
        season_label = (
            context.season_start_date.strftime("%d.%m.%Y")
            if context.season_start_date
            else "не задана"
        )
        profile = (
            f"🗺 Активное поле: <b>{html.escape(context.field_name)}</b>\n"
            f"📍 {context.latitude:.5f}, {context.longitude:.5f}\n"
            f"🌱 Культуры на точке: <b>{crop_names}</b>\n"
            f"✅ Для отчёта выбрана: <b>{selected}</b>\n"
            f"📅 Дата выбранной культуры: {season_label}\n"
            f"📚 Всего полей: {len(fields)}"
        )
    await answer_html(
        message,
        "🌾 <b>Агрометеорологический бот</b>\n\n"
        f"{profile}\n\n"
        "Рабочий путь: поле → культуры → дата и фаза → отчёт или риски.\n"
        "Погодный прогноз относится к координатам поля; сезонные расчёты — к "
        "выбранной культуре.",
        reply_markup=get_main_keyboard(),
    )


@router.callback_query(F.data.startswith("field_open:"))
async def open_field(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        field_id = int((callback.data or "").split(":", 1)[1])
        field = await get_field_summary(session, callback.from_user.id, field_id)
        crops = await list_field_crops(
            session,
            callback.from_user.id,
            field_id=field_id,
        )
    except (ValueError, IndexError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        _field_text(field, crops),
        reply_markup=get_field_actions_keyboard(
            field.field_id,
            is_active=field.is_active,
        ),
    )
