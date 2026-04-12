"""
Клавиатуры для Telegram-бота.
Поддерживает telebot (pyTelegramBotAPI) и aiogram 3.x.
"""
from telebot.types import (
    ReplyKeyboardMarkup as TelebotReplyKeyboardMarkup,
    KeyboardButton as TelebotKeyboardButton,
    InlineKeyboardMarkup as TelebotInlineKeyboardMarkup,
    InlineKeyboardButton as TelebotInlineKeyboardButton
)
from aiogram.types import (
    InlineKeyboardMarkup as AiogramInlineKeyboardMarkup,
    InlineKeyboardButton as AiogramInlineKeyboardButton
)
from src.storage.coordinates import load_coordinates
from src.agro.crop_catalog import CATEGORIES, CROPS


# ── Telebot (pyTelegramBotAPI) ──────────────────────────────────────────────

def create_main_keyboard(user_id=None):
    """Создаёт основную клавиатуру для telebot."""
    keyboard = TelebotReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    has_coords = user_id and load_coordinates(user_id)

    if has_coords:
        keyboard.add(TelebotKeyboardButton("Рекомендации по культурам 🌾"))
        keyboard.add(TelebotKeyboardButton("Климатические данные 📊"))
        keyboard.add(TelebotKeyboardButton("Справочник 📚"))
        keyboard.add(TelebotKeyboardButton("Обновить геолокацию 🔄", request_location=True))
    else:
        keyboard.add(TelebotKeyboardButton("Отправить геолокацию 🌍", request_location=True))
        keyboard.add(TelebotKeyboardButton("Справочник 📚"))

    keyboard.add(TelebotKeyboardButton("Помощь ℹ️"))
    return keyboard


def make_crop_category_keyboard() -> TelebotInlineKeyboardMarkup:
    """Клавиатура выбора категории культуры для telebot."""
    kb = TelebotInlineKeyboardMarkup(row_width=2)
    buttons = []
    for cat_id, cat in CATEGORIES.items():
        buttons.append(
            TelebotInlineKeyboardButton(
                f"{cat['emoji']} {cat['label']}",
                callback_data=f"crop_cat:{cat_id}"
            )
        )
    kb.add(*buttons)
    return kb


def make_crop_list_keyboard(cat_id: str) -> TelebotInlineKeyboardMarkup:
    """Клавиатура выбора конкретной культуры из категории для telebot."""
    kb = TelebotInlineKeyboardMarkup(row_width=2)
    category = CATEGORIES.get(cat_id)
    if not category:
        return kb
    buttons = []
    for crop_key in category["crops"]:
        crop = CROPS.get(crop_key)
        if crop:
            buttons.append(
                TelebotInlineKeyboardButton(
                    f"{crop['emoji']} {crop['name_ru']}",
                    callback_data=f"crop_pick:{crop_key}"
                )
            )
    buttons.append(
        TelebotInlineKeyboardButton("◀️ Назад к категориям", callback_data="crop_back_to_categories")
    )
    kb.add(*buttons)
    return kb


# ── Aiogram 3.x ─────────────────────────────────────────────────────────────

def get_main_keyboard() -> AiogramInlineKeyboardMarkup:
    """Главное меню для aiogram 3.x."""
    return AiogramInlineKeyboardMarkup(inline_keyboard=[
        [AiogramInlineKeyboardButton(text="🌦 Агропрогноз", callback_data="agro_report")],
        [AiogramInlineKeyboardButton(text="📊 Индексы", callback_data="agro_indices")],
        [AiogramInlineKeyboardButton(text="🤖 Агросоветник", callback_data="agro_advisor")],
        [AiogramInlineKeyboardButton(text="📍 Моё поле", callback_data="my_field")],
        [AiogramInlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
    ])


def get_rag_keyboard() -> AiogramInlineKeyboardMarkup:
    """Клавиатура для RAG-сессии (aiogram 3.x)."""
    return AiogramInlineKeyboardMarkup(inline_keyboard=[
        [AiogramInlineKeyboardButton(text="❌ Отмена", callback_data="cancel_rag")],
    ])
