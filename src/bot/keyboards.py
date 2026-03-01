from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from src.storage.coordinates import load_coordinates


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
