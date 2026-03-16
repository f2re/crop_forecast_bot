from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from src.storage.coordinates import load_coordinates
from src.agro.crop_catalog import CATEGORIES, CROPS


def create_main_keyboard(user_id=None):
    """
    Создаёт основную клавиатуру бота.

    Кнопки с координатами:
        - Рекомендации по культурам 🌾
        - Климатические данные 📊
        - Справочник 📚  (поиск по агрометеорологической литературе)
        - Обновить геолокацию 🔄
    Кнопки без координат:
        - Отправить геолокацию 🌍
        - Справочник 📚
    """
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    has_coords = user_id and load_coordinates(user_id)

    if has_coords:
        recommend_button = KeyboardButton("Рекомендации по культурам 🌾")
        climate_button = KeyboardButton("Климатические данные 📊")
        literature_button = KeyboardButton("Справочник 📚")
        location_button = KeyboardButton("Обновить геолокацию 🔄", request_location=True)

        keyboard.add(recommend_button)
        keyboard.add(climate_button)
        keyboard.add(literature_button)
        keyboard.add(location_button)
    else:
        location_button = KeyboardButton("Отправить геолокацию 🌍", request_location=True)
        literature_button = KeyboardButton("Справочник 📚")
        keyboard.add(location_button)
        keyboard.add(literature_button)

    help_button = KeyboardButton("Помощь ℹ️")
    keyboard.add(help_button)

    return keyboard


def make_crop_category_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора категории культуры (6 кнопок)."""
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for cat_id, cat in CATEGORIES.items():
        buttons.append(
            InlineKeyboardButton(
                f"{cat['emoji']} {cat['label']}",
                callback_data=f"crop_cat:{cat_id}"
            )
        )
    kb.add(*buttons)
    return kb


def make_crop_list_keyboard(cat_id: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора конкретной культуры из категории."""
    kb = InlineKeyboardMarkup(row_width=2)
    category = CATEGORIES.get(cat_id)
    if not category:
        return kb
    buttons = []
    for crop_key in category["crops"]:
        crop = CROPS.get(crop_key)
        if crop:
            buttons.append(
                InlineKeyboardButton(
                    f"{crop['emoji']} {crop['name_ru']}",
                    callback_data=f"crop_pick:{crop_key}"
                )
            )
    buttons.append(
        InlineKeyboardButton("◀️ Назад к категориям", callback_data="crop_back_to_categories")
    )
    kb.add(*buttons)
    return kb
