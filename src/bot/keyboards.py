from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from src.storage.coordinates import load_coordinates

def create_main_keyboard(user_id=None):
    """
    Создает основную клавиатуру для взаимодействия с пользователем.

    Args:
        user_id: ID пользователя для проверки наличия координат

    Returns:
        Объект клавиатуры ReplyKeyboardMarkup
    """
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    # Проверяем, есть ли сохраненные координаты
    has_coords = user_id and load_coordinates(user_id)

    if has_coords:
        # Если координаты есть, показываем все опции
        recommend_button = KeyboardButton("Рекомендации по культурам 🌾")
        climate_button = KeyboardButton("Климатические данные 📊")
        location_button = KeyboardButton("Обновить геолокацию 🔄", request_location=True)

        keyboard.add(recommend_button)
        keyboard.add(climate_button)
        keyboard.add(location_button)
    else:
        # Если координат нет, просим отправить геолокацию
        location_button = KeyboardButton("Отправить геолокацию 🌍", request_location=True)
        keyboard.add(location_button)

    # Кнопка помощи всегда доступна
    help_button = KeyboardButton("Помощь ℹ️")
    keyboard.add(help_button)

    return keyboard
