from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.agro.crop_catalog import get_crop_name, get_crop_phases
from src.bot.keyboards import (
    get_field_keyboard,
    get_growth_context_keyboard,
    get_main_keyboard,
    get_phase_keyboard,
    get_season_keyboard,
)
from src.bot.telegram_text import edit_html
from src.database.crud import get_field_context
from src.database.phenology import (
    clear_observed_phase,
    get_active_crop_phenology,
    set_growth_context,
    set_observed_phase,
)
from src.domain.phenology import (
    plant_type_label,
    production_system_label,
    validate_plant_type,
    validate_production_system,
)

router = Router(name="phenology")


def _growth_context_text(profile) -> str:
    lines = [
        "🌾 <b>Условия выращивания</b>",
        f"🗺 Поле: {html.escape(profile.field_name)}",
        f"🌱 Культура: <b>{html.escape(get_crop_name(profile.crop_key))}</b>",
        f"• Грунт: {html.escape(production_system_label(profile.production_system))}",
    ]
    if profile.crop_key == "tomato":
        lines.append(f"• Тип роста: {html.escape(plant_type_label(profile.plant_type))}")
        lines.extend(
            [
                "",
                "Эти сведения понадобятся для будущей проверяемой подсказки "
                "стадии. Сейчас бот не назначает стадию автоматически.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Условия сохраняются как контекст поля. Числовая модель стадии "
                "для этой культуры пока не заявляется.",
            ]
        )
    return "\n".join(lines)


@router.callback_query(F.data == "season_phase")
async def choose_phase(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        f"🌿 <b>Фактическая стадия</b>\n"
        f"Поле: {html.escape(context.field_name)}\n"
        f"Культура: {html.escape(get_crop_name(context.crop_key))}\n\n"
        "Выберите стадию после осмотра растений. Бот сохранит время "
        "подтверждения и позже напомнит перепроверить наблюдение. Это не "
        "автоматический прогноз стадии.",
        reply_markup=get_phase_keyboard(context.crop_key),
    )


@router.callback_query(F.data.startswith("phase_pick:"))
async def save_phase(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    phases = tuple(get_crop_phases(context.crop_key))
    try:
        index = int((callback.data or "").partition(":")[2])
        phase = phases[index]
    except (ValueError, IndexError):
        await callback.answer("Неизвестная стадия", show_alert=True)
        return

    saved = await set_observed_phase(session, callback.from_user.id, phase)
    await callback.answer("Стадия подтверждена")
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        f"✅ <b>Стадия подтверждена: {html.escape(phase)}</b>\n"
        f"Поле: {html.escape(saved.field_name)}\n"
        f"Культура: {html.escape(get_crop_name(saved.crop_key))}\n\n"
        "Сохранено как наблюдение пользователя с текущим временем. Бот не "
        "подменяет осмотр расчётной стадией.",
        reply_markup=get_season_keyboard(
            has_start=saved.season_start_date is not None,
            has_phase=True,
        ),
    )


@router.callback_query(F.data == "phase_confirm_current")
async def confirm_current_phase(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    profile = await get_active_crop_phenology(session, callback.from_user.id)
    if profile is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        return
    if profile.phenological_phase is None:
        await callback.answer("Стадия ещё не указана", show_alert=True)
        return

    saved = await set_observed_phase(
        session,
        callback.from_user.id,
        profile.phenological_phase,
        note=profile.phase_observation_note,
    )
    await callback.answer("Время наблюдения обновлено")
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        f"✅ Стадия <b>{html.escape(saved.phenological_phase or '')}</b> "
        "подтверждена без изменения.\n\n"
        "Дата последнего осмотра обновлена; следующее напоминание будет "
        "основано на давности наблюдения, а не на выдуманном пороге стадии.",
        reply_markup=get_season_keyboard(
            has_start=saved.season_start_date is not None,
            has_phase=True,
        ),
    )


@router.callback_query(F.data == "phase_clear")
async def clear_phase(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        saved = await clear_observed_phase(session, callback.from_user.id)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Стадия удалена")
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        "🧹 Наблюдаемая стадия и время её подтверждения удалены.\n"
        "Новый отчёт не будет предполагать стадию автоматически.",
        reply_markup=get_season_keyboard(
            has_start=saved.season_start_date is not None,
            has_phase=False,
        ),
    )


@router.callback_query(F.data == "crop_growth_context")
async def show_growth_context(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    profile = await get_active_crop_phenology(session, callback.from_user.id)
    await callback.answer()
    if callback.message is None:
        return
    if profile is None:
        await edit_html(
            callback.message,
            "Сначала добавьте поле и культуру.",
            reply_markup=get_field_keyboard(),
        )
        return
    await edit_html(
        callback.message,
        _growth_context_text(profile),
        reply_markup=get_growth_context_keyboard(
            profile.crop_key,
            production_system=profile.production_system,
            plant_type=profile.plant_type,
        ),
    )


@router.callback_query(F.data.startswith("set_production_system:"))
async def save_production_system(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    raw_value = (callback.data or "").partition(":")[2]
    try:
        value = validate_production_system(raw_value)
        profile = await set_growth_context(
            session,
            callback.from_user.id,
            production_system=value,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Условия сохранены")
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        _growth_context_text(profile),
        reply_markup=get_growth_context_keyboard(
            profile.crop_key,
            production_system=profile.production_system,
            plant_type=profile.plant_type,
        ),
    )


@router.callback_query(F.data.startswith("set_plant_type:"))
async def save_plant_type(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    raw_value = (callback.data or "").partition(":")[2]
    try:
        value = validate_plant_type(raw_value)
        profile = await get_active_crop_phenology(session, callback.from_user.id)
        if profile is None:
            raise ValueError("Сначала добавьте поле и культуру.")
        if profile.crop_key != "tomato":
            raise ValueError("Тип роста сейчас используется только для томата.")
        profile = await set_growth_context(
            session,
            callback.from_user.id,
            plant_type=value,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Тип роста сохранён")
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        _growth_context_text(profile),
        reply_markup=get_growth_context_keyboard(
            profile.crop_key,
            production_system=profile.production_system,
            plant_type=profile.plant_type,
        ),
    )


@router.callback_query(F.data == "phenology_back_to_menu")
async def phenology_back_to_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await edit_html(
            callback.message,
            "Выберите действие:",
            reply_markup=get_main_keyboard(),
        )
