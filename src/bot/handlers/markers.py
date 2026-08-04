from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.late_blight_monitoring import (
    acknowledge_manual_late_blight_view,
    enable_open_field_late_blight_monitor,
    require_open_field_late_blight_scope,
    set_open_field_late_blight_inoculum_context,
)
from src.application.late_blight_screening import (
    generate_potato_late_blight_screening,
)
from src.application.ports.late_blight import LateBlightWeatherProviderError
from src.bot.biological_risk_messages import format_crop_biological_risks
from src.bot.keyboards import get_field_keyboard
from src.bot.late_blight_messages import format_potato_late_blight_screening
from src.bot.marker_messages import (
    format_agrometeorological_hazards,
    format_candidate_pest_markers,
    format_marker_catalog_overview,
    format_meteorological_hazards,
    format_operational_pest_markers,
)
from src.bot.telegram_text import answer_html, edit_html
from src.database.biological_monitoring import (
    LateBlightMonitorContext,
    disable_late_blight_monitor,
    get_active_late_blight_context,
)
from src.database.crud import get_field_context
from src.domain.late_blight_delivery import InoculumContext

logger = logging.getLogger(__name__)
router = Router(name="marker-catalog")

_METEOROLOGICAL_SOURCE_URL = (
    "https://method.meteorf.ru/norma/document/nast_shf.pdf"
)
_AGROMETEOROLOGICAL_SOURCE_URL = (
    "https://files.stroyinf.ru/Index2/1/4293728/4293728665.htm"
)
_HUTTON_SOURCE_URL = (
    "https://ahdb.org.uk/knowledge-library/late-blight-management-in-potatoes"
)
_CONTEXT_LABELS: dict[InoculumContext, str] = {
    "unknown": "подтверждённого источника нет",
    "regional_alert_confirmed": "пользователь указал региональное сообщение",
    "nearby_outbreak_confirmed": "пользователь указал подтверждённый очаг рядом",
    "field_source_suspected": "пользователь отметил возможный источник на поле",
    "field_symptoms_observed": "пользователь отметил подозрительные симптомы",
}
_CONTEXT_BUTTONS: tuple[tuple[InoculumContext, str], ...] = (
    ("unknown", "⚪ Нет подтверждённого источника"),
    ("regional_alert_confirmed", "📣 Есть региональное сообщение"),
    ("nearby_outbreak_confirmed", "📍 Очаг подтверждён рядом"),
    ("field_source_suspected", "🥔 Возможный источник на поле"),
    ("field_symptoms_observed", "🔎 Подозрительные симптомы"),
)


def _catalog_keyboard(
    *,
    section: str = "overview",
    crop_key: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if section == "biological" and crop_key == "potato":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🦠 Проверить фитофтороз",
                    callback_data="late_blight:potato",
                )
            ]
        )
    if section != "biological":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🦠 Болезни и вредители культуры",
                    callback_data="marker_catalog:biological",
                )
            ]
        )
    if section != "meteo":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🌪 ОЯ погоды",
                    callback_data="marker_catalog:meteo",
                )
            ]
        )
    if section != "agro":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🌾 Агрометеорологические ОЯ",
                    callback_data="marker_catalog:agro",
                )
            ]
        )
    if section != "pest_active":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🐛 Рабочие маркеры вредителей",
                    callback_data="marker_catalog:pest_active",
                )
            ]
        )
    if section != "pest_candidates":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🧪 Кандидаты без связей",
                    callback_data="marker_catalog:pest_candidates",
                )
            ]
        )
    if section == "meteo":
        rows.append(
            [
                InlineKeyboardButton(
                    text="📄 РД 52.27.724-2019",
                    url=_METEOROLOGICAL_SOURCE_URL,
                )
            ]
        )
    if section == "agro":
        rows.append(
            [
                InlineKeyboardButton(
                    text="📄 Р 52.33.877-2019",
                    url=_AGROMETEOROLOGICAL_SOURCE_URL,
                )
            ]
        )
    if section != "overview":
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️ К обзору каталога",
                    callback_data="marker_catalog",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _late_blight_keyboard(
    *,
    enabled: bool,
    open_field: bool = True,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if open_field:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Пересчитать",
                    callback_data="late_blight:potato",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        "🔕 Выключить предупреждения"
                        if enabled
                        else "🔔 Включить предупреждения"
                    ),
                    callback_data=(
                        "late_blight:disable"
                        if enabled
                        else "late_blight:enable"
                    ),
                )
            ]
        )
        if enabled:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="🧭 Источник инфекции",
                        callback_data="late_blight:context",
                    )
                ]
            )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🌾 Условия выращивания",
                    callback_data="crop_growth_context",
                )
            ]
        )
        if enabled:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="🔕 Выключить старое наблюдение",
                        callback_data="late_blight:disable",
                    )
                ]
            )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="📚 Критерии Hutton",
                    url=_HUTTON_SOURCE_URL,
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ К болезням культуры",
                    callback_data="marker_catalog:biological",
                )
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _late_blight_context_keyboard(
    current: InoculumContext,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for value, label in _CONTEXT_BUTTONS:
        marker = "✅ " if value == current else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker}{label}"[:64],
                    callback_data=f"late_blight:context:set:{value}",
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="◀️ К расчёту фитофтороза",
                    callback_data="late_blight:potato",
                )
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_late_blight_context(
    context: InoculumContext,
) -> str:
    return "\n".join(
        [
            "🧭 <b>Источник инфекции фитофтороза</b>",
            "",
            "Текущий контекст: "
            f"<b>{html.escape(_CONTEXT_LABELS[context])}</b>.",
            "",
            "Выберите только то, что действительно известно:",
            "• региональное сообщение — есть проверяемый источник и дата;",
            "• очаг рядом — заболевание подтверждено специалистом или лабораторией;",
            "• возможный источник — падалица, отбракованные клубни или заражённые "
            "остатки только подозреваются;",
            "• симптомы — пользователь увидел похожие признаки, но диагноз ещё "
            "не подтверждён.",
            "",
            "Контекст может повысить приоритет уведомления при действующем "
            "погодном окне. Он не изменяет критерий Hutton, не доказывает "
            "заражение и не является рекомендацией по обработке.",
        ]
    )


def _with_monitor_status(
    text: str,
    *,
    enabled: bool,
    inoculum_context: InoculumContext,
) -> str:
    status = (
        "🔔 Фоновые предупреждения: <b>включены</b>."
        if enabled
        else "🔕 Фоновые предупреждения: <b>выключены</b>."
    )
    context = (
        "🧭 Контекст: "
        f"{html.escape(_CONTEXT_LABELS[inoculum_context])}."
        if enabled
        else ""
    )
    return "\n\n".join(part for part in (text, status, context) if part)


async def _edit_section(
    callback: CallbackQuery,
    *,
    text: str,
    section: str,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        text,
        reply_markup=_catalog_keyboard(section=section),
    )


async def _show_potato_late_blight(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    context: LateBlightMonitorContext | None = None,
) -> None:
    if callback.message is None:
        return
    resolved = context or await get_active_late_blight_context(
        session,
        callback.from_user.id,
    )
    if resolved is None:
        await edit_html(
            callback.message,
            "Сначала добавьте поле и выберите культуру.",
            reply_markup=get_field_keyboard(),
        )
        return
    if resolved.crop_key != "potato":
        await edit_html(
            callback.message,
            "Погодный расчёт Hutton сейчас реализован только для картофеля. "
            "Модель томата требует отдельной проверки и не переносится "
            "автоматически.",
            reply_markup=_catalog_keyboard(
                section="biological",
                crop_key=resolved.crop_key,
            ),
        )
        return

    try:
        await require_open_field_late_blight_scope(
            session,
            callback.from_user.id,
        )
    except ValueError as exc:
        await edit_html(
            callback.message,
            "🌾 <b>Нужно уточнить условия выращивания</b>\n\n"
            f"{html.escape(str(exc))}\n\n"
            "Наружная температура, точка росы, туман и видимость не описывают "
            "микроклимат теплицы. Для защищённого грунта понадобится датчик "
            "внутри сооружения.",
            reply_markup=_late_blight_keyboard(
                enabled=resolved.enabled,
                open_field=False,
            ),
        )
        return

    await edit_html(
        callback.message,
        f"🦠 Поле <b>{html.escape(resolved.field_name)}</b>\n"
        "Проверяю температуру, влажность и ночное насыщение воздуха…",
    )
    await session.rollback()
    try:
        outlook = await generate_potato_late_blight_screening(
            resolved.latitude,
            resolved.longitude,
        )
    except LateBlightWeatherProviderError as exc:
        await edit_html(
            callback.message,
            "⚠️ Почасовые данные для проверки фитофтороза сейчас недоступны. "
            f"Причина: {html.escape(str(exc))}",
            reply_markup=_late_blight_keyboard(enabled=resolved.enabled),
        )
        return
    except Exception:
        logger.exception(
            "Potato late-blight screening failed for user %s field %s",
            callback.from_user.id,
            resolved.field_id,
        )
        await edit_html(
            callback.message,
            "⚠️ Не удалось проверить погодное окно фитофтороза. "
            "Ошибка записана в журнал сервиса.",
            reply_markup=_late_blight_keyboard(enabled=resolved.enabled),
        )
        return

    if resolved.enabled and outlook.available:
        try:
            await acknowledge_manual_late_blight_view(
                session,
                resolved,
                outlook,
            )
        except Exception:
            logger.exception(
                "Failed to acknowledge manual late-blight view for user %s field %s",
                callback.from_user.id,
                resolved.field_id,
            )

    await edit_html(
        callback.message,
        _with_monitor_status(
            format_potato_late_blight_screening(
                outlook,
                field_name=resolved.field_name,
            ),
            enabled=resolved.enabled,
            inoculum_context=resolved.inoculum_context,
        ),
        reply_markup=_late_blight_keyboard(enabled=resolved.enabled),
    )


@router.message(Command("markers"))
async def marker_catalog_command(message: Message) -> None:
    await answer_html(
        message,
        format_marker_catalog_overview(),
        reply_markup=_catalog_keyboard(),
    )


@router.callback_query(F.data == "marker_catalog")
async def marker_catalog_overview(callback: CallbackQuery) -> None:
    await _edit_section(
        callback,
        text=format_marker_catalog_overview(),
        section="overview",
    )


@router.callback_query(F.data == "marker_catalog:biological")
async def marker_catalog_biological(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    context = await get_field_context(session, callback.from_user.id)
    if context is None:
        await edit_html(
            callback.message,
            "Сначала добавьте поле и выберите культуру.",
            reply_markup=get_field_keyboard(),
        )
        return
    await edit_html(
        callback.message,
        format_crop_biological_risks(context.crop_key),
        reply_markup=_catalog_keyboard(
            section="biological",
            crop_key=context.crop_key,
        ),
    )


@router.callback_query(F.data == "late_blight:potato")
async def potato_late_blight_screening(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await callback.answer()
    await _show_potato_late_blight(callback, session)


@router.callback_query(F.data == "late_blight:enable")
async def enable_potato_late_blight_alerts(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    try:
        context = await enable_open_field_late_blight_monitor(
            session,
            callback.from_user.id,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Предупреждения включены")
    await _show_potato_late_blight(callback, session, context=context)


@router.callback_query(F.data == "late_blight:disable")
async def disable_potato_late_blight_alerts(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    try:
        context = await disable_late_blight_monitor(
            session,
            callback.from_user.id,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Предупреждения выключены")
    if callback.message is None:
        return
    await edit_html(
        callback.message,
        "🔕 <b>Фоновые предупреждения о фитофторозе выключены</b>\n\n"
        "Ручная проверка погодного окна остаётся доступной для подтверждённого "
        "открытого грунта. Уже сохранённые данные не используются для фоновой "
        "рассылки, пока наблюдение не будет включено снова.",
        reply_markup=_late_blight_keyboard(enabled=context.enabled),
    )


@router.callback_query(F.data == "late_blight:context")
async def late_blight_context_menu(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        await require_open_field_late_blight_scope(
            session,
            callback.from_user.id,
        )
        context = await get_active_late_blight_context(
            session,
            callback.from_user.id,
        )
        if context is None or context.monitor_id is None or not context.enabled:
            raise ValueError("Сначала включите предупреждения о фитофторозе.")
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await edit_html(
        callback.message,
        format_late_blight_context(context.inoculum_context),
        reply_markup=_late_blight_context_keyboard(context.inoculum_context),
    )


@router.callback_query(F.data.startswith("late_blight:context:set:"))
async def set_late_blight_context(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    value = (callback.data or "").rsplit(":", maxsplit=1)[-1]
    try:
        context = await set_open_field_late_blight_inoculum_context(
            session,
            callback.from_user.id,
            value,
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    except Exception:
        logger.exception(
            "Failed to update late-blight inoculum context for user %s",
            callback.from_user.id,
        )
        await callback.answer("Не удалось сохранить контекст", show_alert=True)
        return

    message = (
        "Подтверждение источника снято"
        if context.inoculum_context == "unknown"
        else "Контекст сохранён"
    )
    await callback.answer(message)
    await _show_potato_late_blight(callback, session, context=context)


@router.callback_query(F.data == "marker_catalog:meteo")
async def marker_catalog_meteo(callback: CallbackQuery) -> None:
    await _edit_section(
        callback,
        text=format_meteorological_hazards(),
        section="meteo",
    )


@router.callback_query(F.data == "marker_catalog:agro")
async def marker_catalog_agro(callback: CallbackQuery) -> None:
    await _edit_section(
        callback,
        text=format_agrometeorological_hazards(),
        section="agro",
    )


@router.callback_query(F.data == "marker_catalog:pest_active")
async def marker_catalog_pest_active(callback: CallbackQuery) -> None:
    await _edit_section(
        callback,
        text=format_operational_pest_markers(),
        section="pest_active",
    )


@router.callback_query(F.data == "marker_catalog:pest_candidates")
async def marker_catalog_pest_candidates(callback: CallbackQuery) -> None:
    await _edit_section(
        callback,
        text=format_candidate_pest_markers(),
        section="pest_candidates",
    )
