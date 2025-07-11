from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from src.storage.coordinates import load_coordinates

def create_main_keyboard(user_id=None):
    """
    Создает основную клавиатуру для взаимодействия с пользователем.
    Если передан `user_id` и для него есть координаты, добавляет кнопку для запроса климатических данных.

    :param user_id: ID пользователя для проверки наличия координат.
    :return: Объект клавиатуры ReplyKeyboardMarkup.
    """
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("Отправить геолокацию 🌍", request_location=True))

    # Если у пользователя есть сохраненные координаты, добавляем кнопку для климатических данных
    if user_id and load_coordinates(user_id):
        keyboard.add(KeyboardButton("Климатические данные 📊"))

    keyboard.add(KeyboardButton("Помощь ℹ️"))
    return keyboard
