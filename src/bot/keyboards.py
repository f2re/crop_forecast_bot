from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.agro.crop_catalog import CATEGORIES, CROPS, get_crop


def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌦 Агроотчёт", callback_data="agro_report")],
            [InlineKeyboardButton(text="📍 Моё поле", callback_data="my_field")],
            [InlineKeyboardButton(text="🌱 Выбрать культуру", callback_data="crop_choose")],
            [InlineKeyboardButton(text="📅 Сезон и фаза", callback_data="season")],
            [InlineKeyboardButton(text="🤖 Агросоветник", callback_data="agro_advisor")],
            [InlineKeyboardButton(text="⚙️ Уведомления", callback_data="settings")],
        ]
    )


def get_field_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⌨️ Ввести координаты", callback_data="field_manual")],
            [InlineKeyboardButton(text="📱 Отправить геолокацию", callback_data="field_location")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
        ]
    )


def get_location_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Отправьте геолокацию или нажмите «Отмена»",
    )


def get_crop_categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category_id, category in CATEGORIES.items():
        builder.button(
            text=f"{category['emoji']} {category['label']}",
            callback_data=f"crop_cat:{category_id}",
        )
    builder.button(text="◀️ В меню", callback_data="menu")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def get_crop_list_keyboard(category_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    category = CATEGORIES.get(category_id)
    if category:
        for crop_key in category["crops"]:
            crop = CROPS.get(crop_key)
            if crop:
                builder.button(
                    text=f"{crop['emoji']} {crop['name_ru']}",
                    callback_data=f"crop_pick:{crop_key}",
                )
    builder.button(text="◀️ К категориям", callback_data="crop_choose")
    builder.adjust(2)
    return builder.as_markup()


def get_season_keyboard(*, has_start: bool, has_phase: bool) -> InlineKeyboardMarkup:
    date_action = "Изменить дату" if has_start else "Указать дату посева"
    rows = [
        [InlineKeyboardButton(text=f"📅 {date_action}", callback_data="season_start_set")],
        [InlineKeyboardButton(text="🌿 Указать фактическую фазу", callback_data="season_phase")],
        [InlineKeyboardButton(text="🌱 Изменить культуру", callback_data="crop_choose")],
    ]
    if has_phase:
        rows.append(
            [InlineKeyboardButton(text="🧹 Удалить указанную фазу", callback_data="phase_clear")]
        )
    rows.append([InlineKeyboardButton(text="◀️ В меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_phase_keyboard(crop_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    phases = list(get_crop(crop_key).get("gdd_stages", {}).keys())
    for index, phase in enumerate(phases):
        builder.button(text=phase, callback_data=f"phase_pick:{index}")
    builder.button(text="◀️ К сезону", callback_data="season")
    builder.adjust(1)
    return builder.as_markup()


def get_settings_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    action = "Отключить" if enabled else "Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{action} ежедневный отчёт", callback_data="toggle_digest")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="menu")],
        ]
    )


def get_rag_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_rag")],
        ]
    )
