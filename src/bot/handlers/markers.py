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
from src.database.crud import get_field_context

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


def _late_blight_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Пересчитать",
                    callback_data="late_blight:potato",
                )
            ],
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
    if context.crop_key != "potato":
        await edit_html(
            callback.message,
            "Погодный расчёт Hutton сейчас реализован только для картофеля. "
            "Модель томата требует отдельной проверки и не переносится "
            "автоматически.",
            reply_markup=_catalog_keyboard(
                section="biological",
                crop_key=context.crop_key,
            ),
        )
        return

    await edit_html(
        callback.message,
        f"🦠 Поле <b>{html.escape(context.field_name)}</b>\n"
        "Проверяю температуру и высокую влажность по местным суткам…",
    )
    await session.rollback()
    try:
        outlook = await generate_potato_late_blight_screening(
            context.latitude,
            context.longitude,
        )
    except LateBlightWeatherProviderError as exc:
        await edit_html(
            callback.message,
            "⚠️ Почасовые данные для проверки фитофтороза сейчас недоступны. "
            f"Причина: {html.escape(str(exc))}",
            reply_markup=_late_blight_keyboard(),
        )
        return
    except Exception:
        logger.exception(
            "Potato late-blight screening failed for user %s field %s",
            callback.from_user.id,
            context.field_id,
        )
        await edit_html(
            callback.message,
            "⚠️ Не удалось проверить погодное окно фитофтороза. "
            "Ошибка записана в журнал сервиса.",
            reply_markup=_late_blight_keyboard(),
        )
        return

    await edit_html(
        callback.message,
        format_potato_late_blight_screening(
            outlook,
            field_name=context.field_name,
        ),
        reply_markup=_late_blight_keyboard(),
    )


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
