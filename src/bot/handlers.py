from src.bot.keyboards import create_main_keyboard
from src.storage.coordinates import save_coordinates, load_coordinates
from geopy.geocoders import Nominatim

# Инициализация геокодера для получения адреса
geolocator = Nominatim(user_agent="crop_recommendation_bot")

# Функция для получения адреса по координатам
def get_address(latitude, longitude):
    """Получает адрес по координатам с помощью геокодера Nominatim."""
    try:
        location = geolocator.reverse((latitude, longitude), language='ru')
        if location:
            return location.address
        return "Адрес не удалось определить."
    except Exception as e:
        print(f"Ошибка при получении адреса: {e}")
        return "Не удалось получить адрес из-за технической ошибки."

def register_handlers(bot):
    """Регистрирует все обработчики для бота."""
    
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        """Обработчик команды /start. Приветствует пользователя и показывает сохраненные координаты, если есть."""
        user_name = message.from_user.first_name
        user_id = message.from_user.id
        welcome_text = (
            f"Здравствуйте, {user_name}! 👋\n"
            "Я бот, который поможет вам выбрать культуры для посева. "
            "Для начала отправьте свои координаты, чтобы я мог узнать о климате в вашем районе. 🌾\n"
        )
        
        # Проверяем, есть ли сохраненные координаты
        saved_coords = load_coordinates(user_id)
        if saved_coords:
            latitude = saved_coords['latitude']
            longitude = saved_coords['longitude']
            welcome_text += (
                f"У меня уже есть ваши координаты: широта {latitude}, долгота {longitude}. 🌍\n"
                "Я покажу их на карте ниже. Если хотите обновить, отправьте новую геолокацию.\n"
            )
            bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard())
            
            # Отправляем карту с координатами
            bot.send_location(message.chat.id, latitude, longitude)
            
            # Получаем и отправляем адрес
            address = get_address(latitude, longitude)
            address_text = f"Примерный адрес: {address} 🏡"
            bot.send_message(message.chat.id, address_text, reply_markup=create_main_keyboard())
        else:
            welcome_text += "Нажмите на кнопку ниже, чтобы поделиться геолокацией."
            bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard())
    
    @bot.message_handler(content_types=['location'])
    def handle_location(message):
        """Обработчик геолокации. Сохраняет координаты и показывает их на карте с адресом."""
        user_id = message.from_user.id
        latitude = message.location.latitude
        longitude = message.location.longitude
        
        # Сохранение координат
        save_coordinates(user_id, latitude, longitude)
        
        response_text = (
            f"Спасибо! Я сохранил ваши координаты: широта {latitude}, долгота {longitude}. 🌍\n"
            "Вот они на карте. Скоро я проанализирую климатические данные и дам рекомендации по культурам. 🌱"
        )
        bot.send_message(message.chat.id, response_text, reply_markup=create_main_keyboard())
        
        # Отправляем карту с координатами
        bot.send_location(message.chat.id, latitude, longitude)
        
        # Получаем и отправляем адрес
        address = get_address(latitude, longitude)
        address_text = f"Примерный адрес: {address} 🏡"
        bot.send_message(message.chat.id, address_text, reply_markup=create_main_keyboard())
    
    @bot.message_handler(func=lambda message: message.text == "Помощь ℹ️")
    def send_help(message):
        """Обработчик команды помощи. Показывает инструкции по использованию бота."""
        help_text = (
            "Я помогу вам выбрать культуры для посева на основе климата в вашем районе. 🌾\n"
            "Просто отправьте свою геолокацию, нажав на кнопку 'Отправить геолокацию 🌍'.\n"
            "Если у вас возникнут вопросы, пишите мне!"
        )
        bot.send_message(message.chat.id, help_text, reply_markup=create_main_keyboard())
