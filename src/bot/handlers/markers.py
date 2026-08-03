from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.bot.marker_messages import (
    format_agrometeorological_hazards,
    format_candidate_pest_markers,
    format_marker_catalog_overview,
    format_meteorological_hazards,
    format_operational_pest_markers,
)
from src.bot.telegram_text import answer_html, edit_html
from src.domain.marker_catalog import (
    AGROMETEOROLOGICAL_HAZARD_REFERENCE,
    METEOROLOGICAL_HAZARD_SOURCE,
)

router = Router(name="marker-catalog")


def _catalog_keyboard(*, section: str = "overview") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
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
                    url=METEOROLOGICAL_HAZARD_SOURCE.url,
                )
            ]
        )
    if section == "agro":
        rows.append(
            [
                InlineKeyboardButton(
                    text="📄 Р 52.33.877-2019",
                    url=AGROMETEOROLOGICAL_HAZARD_REFERENCE.url,
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
