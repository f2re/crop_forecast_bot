from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.keyboards import get_report_result_keyboard
from src.domain.pests import PestModel


def get_report_result_with_pests_keyboard() -> InlineKeyboardMarkup:
    base = get_report_result_keyboard()
    rows = list(base.inline_keyboard)
    menu_row = rows.pop() if rows else []
    rows.append(
        [
            InlineKeyboardButton(
                text="🐛 Вредители",
                callback_data="pest_overview",
            )
        ]
    )
    if menu_row:
        rows.append(menu_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_pest_models_keyboard(
    models: Sequence[PestModel],
    *,
    active_pest_key: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for model in models:
        marker = "✅ " if model.key == active_pest_key else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker}{model.name_ru}",
                    callback_data=f"pest_select:{model.key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_pest_unavailable_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌱 Выбрать другую культуру",
                    callback_data="crop_choose",
                )
            ],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
        ]
    )


def get_pest_monitor_keyboard(
    model: PestModel,
    *,
    configured: bool,
    enabled: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if configured and enabled:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="🔄 Пересчитать",
                        callback_data=f"pest_refresh:{model.key}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📅 Изменить первую находку",
                        callback_data=f"pest_setup:{model.key}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔕 Отключить напоминания",
                        callback_data=f"pest_disable:{model.key}",
                    )
                ],
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        "🔔 Включить наблюдение"
                        if configured
                        else "📅 Указать первую находку"
                    ),
                    callback_data=f"pest_setup:{model.key}",
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="ℹ️ Как это считается",
                    callback_data=f"pest_help:{model.key}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 Исходный материал",
                    url=model.source_url,
                )
            ],
            [InlineKeyboardButton(text="◀️ К вредителям", callback_data="pest_overview")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_pest_help_keyboard(model: PestModel) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📚 Открыть источник",
                    url=model.source_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ К расчёту",
                    callback_data=f"pest_select:{model.key}",
                )
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        ]
    )
