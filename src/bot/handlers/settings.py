from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import (
    get_field_keyboard,
    get_quiet_hours_keyboard,
    get_risk_delivery_mode_keyboard,
    get_settings_keyboard,
)
from src.database.crud import get_field_context, set_field_notifications
from src.database.risk_delivery_preferences import (
    RiskDeliveryPreferences,
    get_risk_delivery_preferences,
    set_risk_delivery_mode,
    set_risk_quiet_hours,
)
from src.domain.risk_delivery import quiet_hours_label, risk_delivery_mode_label

router = Router(name="settings")


def parse_setting_callback(data: str | None, prefix: str) -> tuple[int, bool]:
    """Parse ``prefix:field_id:0|1`` callback data."""
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != prefix or parts[2] not in {"0", "1"}:
        raise ValueError("Некорректная команда настройки.")
    try:
        field_id = int(parts[1])
    except ValueError as exc:
        raise ValueError("Некорректный идентификатор поля.") from exc
    if field_id <= 0:
        raise ValueError("Некорректный идентификатор поля.")
    return field_id, parts[2] == "1"


def _parse_field_callback(data: str | None, prefix: str) -> int:
    parts = (data or "").split(":")
    if len(parts) != 2 or parts[0] != prefix:
        raise ValueError("Некорректная команда настройки.")
    try:
        field_id = int(parts[1])
    except ValueError as exc:
        raise ValueError("Некорректный идентификатор поля.") from exc
    if field_id <= 0:
        raise ValueError("Некорректный идентификатор поля.")
    return field_id


def parse_risk_mode_callback(data: str | None) -> tuple[int, str]:
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != "set_risk_mode":
        raise ValueError("Некорректная команда режима доставки.")
    try:
        field_id = int(parts[1])
    except ValueError as exc:
        raise ValueError("Некорректный идентификатор поля.") from exc
    if field_id <= 0:
        raise ValueError("Некорректный идентификатор поля.")
    return field_id, parts[2]


def parse_quiet_hours_callback(
    data: str | None,
) -> tuple[int, int | None, int | None]:
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != "set_quiet_hours":
        raise ValueError("Некорректная команда тихих часов.")
    try:
        field_id = int(parts[1])
    except ValueError as exc:
        raise ValueError("Некорректный идентификатор поля.") from exc
    if field_id <= 0:
        raise ValueError("Некорректный идентификатор поля.")
    presets = {
        "off": (None, None),
        "22-07": (22, 7),
        "23-06": (23, 6),
    }
    if parts[2] not in presets:
        raise ValueError("Неизвестный пресет тихих часов.")
    start_hour, end_hour = presets[parts[2]]
    return field_id, start_hour, end_hour


async def _show_settings(
    callback: CallbackQuery,
    context,
    preferences: RiskDeliveryPreferences,
) -> None:
    if callback.message is None:
        return
    await callback.message.edit_text(
        "⚙️ <b>Уведомления активного поля</b>\n"
        f"🗺 {html.escape(context.field_name)}\n"
        f"📨 Ежедневный агроотчёт: "
        f"{'включён' if context.daily_digest else 'выключен'}\n"
        f"⚠️ Погодные риски: {'включены' if context.frost_alerts else 'выключены'}\n"
        f"📬 Режим: {risk_delivery_mode_label(preferences.mode)}\n"
        f"🌙 Тихие часы: {quiet_hours_label(preferences.quiet_hours_start, preferences.quiet_hours_end)}\n\n"
        "Высокий риск доставляется без ожидания тихих часов или суточного дайджеста.",
        reply_markup=get_settings_keyboard(
            field_id=context.field_id,
            daily_digest_enabled=context.daily_digest,
            frost_alerts_enabled=context.frost_alerts,
            risk_delivery_mode=preferences.mode,
            quiet_hours_start=preferences.quiet_hours_start,
            quiet_hours_end=preferences.quiet_hours_end,
        ),
    )


async def _current_context(
    callback: CallbackQuery,
    session: AsyncSession,
    field_id: int | None = None,
):
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await callback.answer("Сначала добавьте поле", show_alert=True)
        if callback.message is not None:
            await callback.message.edit_text(
                "Сначала добавьте поле.",
                reply_markup=get_field_keyboard(),
            )
        return None
    if field_id is not None and context.field_id != field_id:
        await callback.answer(
            "Эта кнопка относится к другому полю. Откройте настройки снова.",
            show_alert=True,
        )
        return None
    return context


async def _preferences(
    session: AsyncSession,
    callback: CallbackQuery,
    field_id: int,
) -> RiskDeliveryPreferences:
    return await get_risk_delivery_preferences(
        session,
        telegram_id=callback.from_user.id,
        field_id=field_id,
    )


@router.callback_query(F.data == "settings")
async def settings(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await _current_context(callback, session)
    if context is None:
        return
    preferences = await _preferences(session, callback, context.field_id)
    await callback.answer()
    await _show_settings(callback, context, preferences)


@router.callback_query(F.data.startswith("set_digest:"))
async def set_digest(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        field_id, enabled = parse_setting_callback(callback.data, "set_digest")
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    context = await _current_context(callback, session, field_id)
    if context is None:
        return
    context = await set_field_notifications(
        session,
        callback.from_user.id,
        daily_digest=enabled,
    )
    preferences = await _preferences(session, callback, field_id)
    await callback.answer(
        f"Ежедневный агроотчёт {'включён' if enabled else 'выключен'}"
    )
    await _show_settings(callback, context, preferences)


@router.callback_query(F.data.startswith("set_frost:"))
async def set_frost(callback: CallbackQuery, session: AsyncSession) -> None:
    """Keep the stable callback/DB field while widening its user-facing meaning."""
    try:
        field_id, enabled = parse_setting_callback(callback.data, "set_frost")
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    context = await _current_context(callback, session, field_id)
    if context is None:
        return
    context = await set_field_notifications(
        session,
        callback.from_user.id,
        frost_alerts=enabled,
    )
    preferences = await _preferences(session, callback, field_id)
    await callback.answer(
        f"Предупреждения о погодных рисках {'включены' if enabled else 'выключены'}"
    )
    await _show_settings(callback, context, preferences)


@router.callback_query(F.data.startswith("risk_mode_menu:"))
async def risk_mode_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        field_id = _parse_field_callback(callback.data, "risk_mode_menu")
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    context = await _current_context(callback, session, field_id)
    if context is None or callback.message is None:
        return
    preferences = await _preferences(session, callback, field_id)
    await callback.answer()
    await callback.message.edit_text(
        "📬 <b>Режим доставки погодных рисков</b>\n\n"
        "«Сразу» сообщает новое сочетание риска, даты и уровня. "
        "«Дайджест» отправляет одну сводку в локальные сутки. "
        "«Только высокий» скрывает уровни наблюдения и повышенный.",
        reply_markup=get_risk_delivery_mode_keyboard(field_id, preferences.mode),
    )


@router.callback_query(F.data.startswith("set_risk_mode:"))
async def set_risk_mode(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        field_id, mode = parse_risk_mode_callback(callback.data)
        context = await _current_context(callback, session, field_id)
        if context is None:
            return
        preferences = await set_risk_delivery_mode(
            session,
            telegram_id=callback.from_user.id,
            field_id=field_id,
            mode=mode,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer(f"Режим: {risk_delivery_mode_label(preferences.mode)}")
    await _show_settings(callback, context, preferences)


@router.callback_query(F.data.startswith("quiet_hours_menu:"))
async def quiet_hours_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        field_id = _parse_field_callback(callback.data, "quiet_hours_menu")
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    context = await _current_context(callback, session, field_id)
    if context is None or callback.message is None:
        return
    preferences = await _preferences(session, callback, field_id)
    await callback.answer()
    await callback.message.edit_text(
        "🌙 <b>Тихие часы поля</b>\n\n"
        "Время локальное для поля. Уровни «наблюдение» и «повышенный» "
        "откладываются; высокий риск доставляется сразу.",
        reply_markup=get_quiet_hours_keyboard(
            field_id,
            preferences.quiet_hours_start,
            preferences.quiet_hours_end,
        ),
    )


@router.callback_query(F.data.startswith("set_quiet_hours:"))
async def set_quiet_hours(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        field_id, start_hour, end_hour = parse_quiet_hours_callback(callback.data)
        context = await _current_context(callback, session, field_id)
        if context is None:
            return
        preferences = await set_risk_quiet_hours(
            session,
            telegram_id=callback.from_user.id,
            field_id=field_id,
            start_hour=start_hour,
            end_hour=end_hour,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    label = quiet_hours_label(
        preferences.quiet_hours_start,
        preferences.quiet_hours_end,
    )
    await callback.answer(f"Тихие часы: {label}")
    await _show_settings(callback, context, preferences)


@router.callback_query(F.data.in_({"toggle_digest", "toggle_frost"}))
async def reject_legacy_toggle(callback: CallbackQuery) -> None:
    """Prevent old inline keyboards from replaying non-idempotent toggles."""
    await callback.answer(
        "Кнопка устарела. Откройте раздел «Уведомления» снова.",
        show_alert=True,
    )
