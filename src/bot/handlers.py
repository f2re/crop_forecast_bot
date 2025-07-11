from src.bot.keyboards import create_main_keyboard
from src.storage.coordinates import save_coordinates, load_coordinates
from geopy.geocoders import Nominatim
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from src.api.era5_ag import get_climate_data
from src.bot.plotting import plot_climate_data
from datetime import datetime, timedelta

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
            bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard(user_id))
            
            # Отправляем карту с координатами
            bot.send_location(message.chat.id, latitude, longitude)
            
            # Получаем и отправляем адрес
            address = get_address(latitude, longitude)
            address_text = f"Примерный адрес: {address} 🏡"
            bot.send_message(message.chat.id, address_text, reply_markup=create_main_keyboard(user_id))
        else:
            welcome_text += "Нажмите на кнопку ниже, чтобы поделиться геолокацией."
            bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard(user_id))
    
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
        bot.send_message(message.chat.id, response_text, reply_markup=create_main_keyboard(user_id))
        
        # Отправляем карту с координатами
        bot.send_location(message.chat.id, latitude, longitude)
        
        # Получаем и отправляем адрес
        address = get_address(latitude, longitude)
        address_text = f"Примерный адрес: {address} 🏡"
        bot.send_message(message.chat.id, address_text, reply_markup=create_main_keyboard(user_id))
    
    @bot.message_handler(func=lambda message: message.text == "Помощь ℹ️")
    def send_help(message):
        """Обработчик команды помощи. Показывает инструкции по использованию бота."""
        user_id = message.from_user.id
        help_text = (
            "Я помогу вам выбрать культуры для посева на основе климата в вашем районе. 🌾\n"
            "Просто отправьте свою геолокацию, нажав на кнопку 'Отправить геолокацию 🌍'.\n"
            "Если у вас возникнут вопросы, пишите мне!"
        )
        bot.send_message(message.chat.id, help_text, reply_markup=create_main_keyboard(user_id))

    @bot.message_handler(func=lambda message: message.text == "Климатические данные 📊")
    def handle_climate_data(message):
        """Обработчик кнопки 'Климатические данные 📊'. Предлагает выбрать период для анализа."""
        user_id = message.from_user.id
        if not load_coordinates(user_id):
            bot.send_message(message.chat.id, "Сначала отправьте свои координаты.", reply_markup=create_main_keyboard(user_id))
            return

        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("За последний месяц", callback_data="climate_last_month"),
            InlineKeyboardButton("За последний год", callback_data="climate_last_year"),
            InlineKeyboardButton("За последние 5 лет", callback_data="climate_5_years")
        )
        bot.send_message(message.chat.id, "Выберите период для анализа климатических данных:", reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('climate_'))
    def handle_climate_callback(call):
        """
        Обработчик для inline-кнопок выбора периода климатических данных.
        Запрашивает данные, строит график и отправляет его пользователю.
        """
        user_id = call.from_user.id
        coords = load_coordinates(user_id)

        if not coords:
            bot.answer_callback_query(call.id, "Координаты не найдены. Пожалуйста, отправьте их снова.")
            return

        bot.answer_callback_query(call.id, "Запрос принят! Загружаю данные... Это может занять некоторое время. ⏳")
        bot.edit_message_text("Пожалуйста, подождите, я готовлю ваш график... ⏳", call.message.chat.id, call.message.message_id)

        # Определяем период
        today = datetime.now()
        if call.data == 'climate_last_month':
            start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
        elif call.data == 'climate_last_year':
            start_date = (today - timedelta(days=365)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
        elif call.data == 'climate_5_years':
            start_date = (today - timedelta(days=5*365)).strftime('%Y-%m-%d')
            end_date = today.strftime('%Y-%m-%d')
        else:
            return

        try:
            # Получаем путь к файлу с данными
            netcdf_file = get_climate_data(coords['latitude'], coords['longitude'], start_date, end_date)

            if netcdf_file:
                bot.edit_message_text("Данные загружены. Создаю график... 🎨", call.message.chat.id, call.message.message_id)
                # Строим график из файла
                plot_image = plot_climate_data(netcdf_file)

                if plot_image:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                    bot.send_photo(call.message.chat.id, plot_image, caption=f"Климатические данные за период с {start_date} по {end_date}")
                else:
                    bot.edit_message_text("Не удалось построить график. Проверьте данные.", call.message.chat.id, call.message.message_id)
            else:
                bot.edit_message_text("Не удалось получить климатические данные. Попробуйте позже.", call.message.chat.id, call.message.message_id)
        except Exception as e:
            print(f"Ошибка в handle_climate_callback: {e}")
            bot.edit_message_text("Произошла ошибка при обработке вашего запроса.", call.message.chat.id, call.message.message_id)
