from telebot.types import ReplyKeyboardMarkup, KeyboardButton

def create_main_keyboard():
    """Создает основную клавиатуру для взаимодействия с пользователем."""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("Отправить геолокацию 🌍", request_location=True))
    keyboard.add(KeyboardButton("Помощь ℹ️"))
    return keyboard
