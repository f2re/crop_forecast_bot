from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.agro.crop_catalog import CATEGORIES, CROPS, get_crop_name
from src.database.crops import FieldCropProfile


def get_crop_manager_keyboard(
    crops: Sequence[FieldCropProfile],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    selected_id: int | None = None
    for crop in crops:
        if crop.is_selected:
            selected_id = crop.season_id
        marker = "✅" if crop.is_selected else "▫️"
        suffix = " · выбран для отчёта" if crop.is_selected else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker} {get_crop_name(crop.crop_key)}{suffix}"[:64],
                    callback_data=f"crop_select:{crop.season_id}",
                )
            ]
        )

    rows.append(
        [InlineKeyboardButton(text="➕ Добавить культуру", callback_data="crop_add")]
    )
    if len(crops) > 1 and selected_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Удалить выбранную культуру",
                    callback_data=f"crop_remove:{selected_id}",
                )
            ]
        )
    if selected_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📅 Сезон и фаза выбранной культуры",
                    callback_data="season",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_crop_add_categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category_id, category in CATEGORIES.items():
        builder.button(
            text=f"{category['emoji']} {category['label']}",
            callback_data=f"crop_add_cat:{category_id}",
        )
    builder.button(text="◀️ К культурам поля", callback_data="crop_choose")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def get_crop_add_list_keyboard(category_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    category = CATEGORIES.get(category_id)
    if category:
        for crop_key in category["crops"]:
            crop = CROPS.get(str(crop_key))
            if crop:
                builder.button(
                    text=f"{crop['emoji']} {crop['name_ru']}",
                    callback_data=f"crop_add_pick:{crop_key}",
                )
    builder.button(text="◀️ К категориям", callback_data="crop_add")
    builder.adjust(2)
    return builder.as_markup()
