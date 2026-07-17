from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import get_field_keyboard, get_settings_keyboard
from src.database.crud import get_field_context, set_field_notifications

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


async def _show_settings(callback: CallbackQuery, context) -> None:
    await callback.message.edit_text(
        "⚙️ <b>Уведомления активного поля</b>\n"
        f"🗺 {html.escape(context.field_name)}\n"
        f"📨 Ежедневный отчёт: {'включён' if context.daily_digest else 'выключен'}\n"
        f"⚠️ Погодные риски: {'включены' if context.frost_alerts else 'выключены'}",
        reply_markup=get_settings_keyboard(
            field_id=context.field_id,
            daily_digest_enabled=context.daily_digest,
            frost_alerts_enabled=context.frost_alerts,
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


@router.callback_query(F.data == "settings")
async def settings(callback: CallbackQuery, session: AsyncSession) -> None:
    context = await _current_context(callback, session)
    if context is None:
        return
    await callback.answer()
    await _show_settings(callback, context)


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
    await callback.answer(
        f"Ежедневный отчёт {'включён' if enabled else 'выключен'}"
    )
    await _show_settings(callback, context)


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
    await callback.answer(
        f"Предупреждения о погодных рисках {'включены' if enabled else 'выключены'}"
    )
    await _show_settings(callback, context)


@router.callback_query(F.data.in_({"toggle_digest", "toggle_frost"}))
async def reject_legacy_toggle(callback: CallbackQuery) -> None:
    """Prevent old inline keyboards from replaying non-idempotent toggles."""
    await callback.answer(
        "Кнопка устарела. Откройте раздел «Уведомления» снова.",
        show_alert=True,
    )
