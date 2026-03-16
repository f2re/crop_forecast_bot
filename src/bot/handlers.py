from src.bot.keyboards import create_main_keyboard, make_crop_category_keyboard, make_crop_list_keyboard
from src.storage.coordinates import save_coordinates, load_coordinates
from geopy.geocoders import Nominatim
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from src.api.era5_ag import get_climate_data
from src.bot.plotting import plot_climate_data
from src.bot.crop_recommender_handler import handle_crop_recommendation_request
from src.agro.crop_catalog import get_crop_name, CROPS
from datetime import datetime, timedelta
import re
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

geolocator = Nominatim(user_agent="crop_recommendation_bot")

# Словарь для хранения состояний пользователей (in-memory)
# Значения: None | 'waiting_for_location_recommendation' | 'waiting_for_text_coordinates'
user_states = {}

# Словарь pending crops: ожидаем подтверждения/смены культуры
# {user_id: {'chat_id': int, 'lat': float, 'lon': float}}
pending_crop_selection = {}


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


def _send_crop_selection_or_run(bot, chat_id, user_id, lat, lon):
    """
    Общая логика после получения координат:
    - если культура уже выбрана → предложить «Продолжить» или «Изменить»
    - если нет → сразу показать выбор категории
    """
    from src.storage.coordinates import load_coordinates as _lc
    # Проверяем сохранённую культуру через in-memory fallback
    # (полноценная БД: вызывается get_user_crop через async сессию в реальном деплое)
    saved_crop = user_states.get(f"crop_{user_id}")  # in-memory crop store

    # Сохраняем координаты для последующего использования в callback
    pending_crop_selection[user_id] = {'chat_id': chat_id, 'lat': lat, 'lon': lon}

    if saved_crop and saved_crop in CROPS:
        crop_name = get_crop_name(saved_crop)
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton(
                f"▶️ Продолжить с культурой: {crop_name}",
                callback_data=f"crop_pick:{saved_crop}"
            ),
            InlineKeyboardButton(
                "🔄 Изменить культуру",
                callback_data="crop_change"
            )
        )
        bot.send_message(
            chat_id,
            f"Ваша текущая культура: {CROPS[saved_crop]['emoji']} {crop_name}\n"
            "Продолжить анализ или выбрать другую?",
            reply_markup=kb
        )
    else:
        bot.send_message(
            chat_id,
            "🌾 Выберите категорию культуры:",
            reply_markup=make_crop_category_keyboard()
        )


def register_handlers(bot):
    """Регистрирует все обработчики для бота."""

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        user_name = message.from_user.first_name
        user_id = message.from_user.id
        welcome_text = (
            f"Здравствуйте, {user_name}! 👋\n"
            "Я бот, который поможет вам выбрать культуры для посева. "
            "Для начала отправьте свои координаты, чтобы я мог узнать о климате в вашем районе. 🌾\n"
        )

        saved_coords = load_coordinates(user_id)
        if saved_coords:
            latitude = saved_coords['latitude']
            longitude = saved_coords['longitude']
            welcome_text += (
                f"У меня уже есть ваши координаты: широта {latitude}, долгота {longitude}. 🌍\n"
                "Я покажу их на карте ниже. Если хотите обновить, отправьте новую геолокацию.\n"
            )
            bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard(user_id))
            bot.send_location(message.chat.id, latitude, longitude)
            address = get_address(latitude, longitude)
            bot.send_message(message.chat.id, f"Примерный адрес: {address} 🏡", reply_markup=create_main_keyboard(user_id))
        else:
            welcome_text += "Нажмите на кнопку ниже, чтобы поделиться геолокацией."
            bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard(user_id))

    @bot.message_handler(content_types=['location'])
    def handle_location(message):
        user_id = message.from_user.id
        latitude = message.location.latitude
        longitude = message.location.longitude
        username = message.from_user.username
        first_name = message.from_user.first_name

        logger.info(f"📍 Получена геолокация от пользователя {user_id}: {latitude}, {longitude}")

        save_coordinates(user_id, latitude, longitude, username=username, first_name=first_name)

        response_text = f"Спасибо! Я сохранил ваши координаты: широта {latitude}, долгота {longitude}. 🌍\n"
        bot.send_message(message.chat.id, response_text, reply_markup=create_main_keyboard(user_id))
        bot.send_location(message.chat.id, latitude, longitude)

        address = get_address(latitude, longitude)
        bot.send_message(message.chat.id, f"Примерный адрес: {address} 🏡")

        if user_states.get(user_id) == 'waiting_for_location_recommendation':
            logger.info(f"🚀 Запуск выбора культуры для пользователя {user_id}")
            user_states[user_id] = None
            _send_crop_selection_or_run(bot, message.chat.id, user_id, latitude, longitude)

    @bot.message_handler(func=lambda message: message.text == "Помощь ℹ️")
    def send_help(message):
        user_id = message.from_user.id
        help_text = (
            "Я помогу вам выбрать культуры для посева на основе климата в вашем районе. 🌾\n"
            "Просто отправьте свою геолокацию, нажав на кнопку 'Отправить геолокацию 🌍'.\n"
            "Если у вас возникнут вопросы, пишите мне!"
        )
        bot.send_message(message.chat.id, help_text, reply_markup=create_main_keyboard(user_id))

    @bot.message_handler(func=lambda message: message.text == "Климатические данные 📊")
    def handle_climate_data(message):
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
        user_id = call.from_user.id
        coords = load_coordinates(user_id)

        if not coords:
            bot.answer_callback_query(call.id, "Координаты не найдены. Пожалуйста, отправьте их снова.")
            return

        bot.answer_callback_query(call.id, "Запрос принят! Загружаю данные... Это может занять некоторое время. ⏳")
        bot.edit_message_text("Пожалуйста, подождите, я готовлю ваш график... ⏳", call.message.chat.id, call.message.message_id)

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
            netcdf_file = get_climate_data(coords['latitude'], coords['longitude'], start_date, end_date)
            if netcdf_file:
                bot.edit_message_text("Данные загружены. Создаю график... 🎨", call.message.chat.id, call.message.message_id)
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

    @bot.message_handler(func=lambda message: message.text == "Рекомендации по культурам 🌾")
    def handle_crop_recommendations(message):
        user_id = message.from_user.id
        coords = load_coordinates(user_id)

        logger.info(f"🌾 Пользователь {user_id} запросил рекомендации по культурам")

        if coords:
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton("Использовать сохраненные координаты", callback_data="use_saved_coords"),
                InlineKeyboardButton("Отправить новую геолокацию", callback_data="send_new_location"),
                InlineKeyboardButton("Ввести координаты вручную", callback_data="enter_coords_manually")
            )
            bot.send_message(
                message.chat.id,
                f"У меня есть ваши координаты: {coords['latitude']:.4f}, {coords['longitude']:.4f}\n"
                "Выберите действие:",
                reply_markup=keyboard
            )
        else:
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton("Отправить геолокацию (мобильное приложение)", callback_data="send_new_location"),
                InlineKeyboardButton("Ввести координаты вручную", callback_data="enter_coords_manually")
            )
            bot.send_message(
                message.chat.id,
                "Для получения рекомендаций по культурам мне нужны ваши координаты.\n\n"
                "📱 На мобильном: отправьте геолокацию\n"
                "💻 На компьютере: введите координаты вручную",
                reply_markup=keyboard
            )

    @bot.callback_query_handler(func=lambda call: call.data == 'use_saved_coords')
    def use_saved_coordinates(call):
        user_id = call.from_user.id
        coords = load_coordinates(user_id)

        if coords:
            bot.answer_callback_query(call.id, "Координаты найдены!")
            bot.delete_message(call.message.chat.id, call.message.message_id)
            _send_crop_selection_or_run(bot, call.message.chat.id, user_id, coords['latitude'], coords['longitude'])
        else:
            bot.answer_callback_query(call.id, "Координаты не найдены")
            bot.send_message(call.message.chat.id, "Координаты не найдены. Пожалуйста, отправьте геолокацию.")

    @bot.callback_query_handler(func=lambda call: call.data == 'send_new_location')
    def request_new_location(call):
        user_id = call.from_user.id
        logger.info(f"📍 Пользователь {user_id} выбрал отправку геолокации")

        bot.answer_callback_query(call.id, "Отправьте геолокацию")
        bot.delete_message(call.message.chat.id, call.message.message_id)

        user_states[user_id] = 'waiting_for_location_recommendation'

        location_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        location_button = KeyboardButton("Отправить геолокацию 🌍", request_location=True)
        cancel_button = KeyboardButton("Отмена ❌")
        location_keyboard.add(location_button)
        location_keyboard.add(cancel_button)

        bot.send_message(
            call.message.chat.id,
            "📱 Нажмите кнопку ниже для отправки геолокации\n\n"
            "⚠️ Внимание: кнопка работает только в мобильном приложении Telegram!\n"
            "На компьютере используйте 'Ввести координаты вручную'",
            reply_markup=location_keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data == 'enter_coords_manually')
    def enter_coords_manually(call):
        user_id = call.from_user.id
        logger.info(f"✍️ Пользователь {user_id} выбрал ручной ввод координат")

        bot.answer_callback_query(call.id, "Введите координаты")
        bot.delete_message(call.message.chat.id, call.message.message_id)

        user_states[user_id] = 'waiting_for_text_coordinates'

        cancel_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        cancel_keyboard.add(KeyboardButton("Отмена ❌"))

        bot.send_message(
            call.message.chat.id,
            "💻 Введите координаты в одном из форматов:\n\n"
            "• <code>55.7558, 37.6173</code> (широта, долгота)\n"
            "• <code>55.7558 37.6173</code> (через пробел)\n"
            "• <code>55°45'20.9\"N 37°37'02.3\"E</code> (градусы)\n\n"
            "Пример: <code>55.7558, 37.6173</code>",
            parse_mode='HTML',
            reply_markup=cancel_keyboard
        )

    # ── Обработчики выбора культуры ──────────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data.startswith('crop_cat:'))
    def handle_crop_category(call):
        """Показывает список культур выбранной категории."""
        cat_id = call.data.split(':', 1)[1]
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"Выберите культуру:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=make_crop_list_keyboard(cat_id)
        )

    @bot.callback_query_handler(func=lambda call: call.data == 'crop_back_to_categories')
    def handle_crop_back(call):
        """Возвращает к выбору категории."""
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🌾 Выберите категорию культуры:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=make_crop_category_keyboard()
        )

    @bot.callback_query_handler(func=lambda call: call.data == 'crop_change')
    def handle_crop_change(call):
        """Показывает категории для смены культуры."""
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🌾 Выберите категорию культуры:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=make_crop_category_keyboard()
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('crop_pick:'))
    def handle_crop_pick(call):
        """Сохраняет выбранную культуру и запускает анализ."""
        user_id = call.from_user.id
        crop_key = call.data.split(':', 1)[1]

        if crop_key not in CROPS:
            bot.answer_callback_query(call.id, "Неизвестная культура.")
            return

        # Сохраняем в in-memory store
        user_states[f"crop_{user_id}"] = crop_key
        crop_name = get_crop_name(crop_key)

        bot.answer_callback_query(call.id, f"Выбрано: {crop_name}")
        bot.delete_message(call.message.chat.id, call.message.message_id)

        # Получаем сохранённые координаты для этого пользователя
        pending = pending_crop_selection.get(user_id)
        if not pending:
            # Попробуем из load_coordinates (если пришли через use_saved_coords)
            coords = load_coordinates(user_id)
            if coords:
                pending = {'chat_id': call.message.chat.id, 'lat': coords['latitude'], 'lon': coords['longitude']}
            else:
                bot.send_message(call.message.chat.id, "❌ Координаты не найдены. Начните заново через 'Рекомендации по культурам 🌾'.")
                return

        # Создаём FakeMessage для обработчика
        class FakeLocation:
            def __init__(self, lat, lon):
                self.latitude = lat
                self.longitude = lon

        class FakeMessage:
            def __init__(self, chat_id, uid, lat, lon):
                self.chat = type('obj', (object,), {'id': chat_id})
                self.from_user = type('obj', (object,), {'id': uid})
                self.location = FakeLocation(lat, lon)

        fake_msg = FakeMessage(pending['chat_id'], user_id, pending['lat'], pending['lon'])

        bot.send_message(
            pending['chat_id'],
            f"🌱 Культура: {CROPS[crop_key]['emoji']} {crop_name}\n🔄 Начинаю анализ данных..."
        )

        try:
            handle_crop_recommendation_request(bot, fake_msg, crop=crop_key)
        except Exception as e:
            logger.error(f"Ошибка анализа после выбора культуры: {e}", exc_info=True)
            bot.send_message(pending['chat_id'], f"Произошла ошибка: {str(e)}")

        # Очищаем pending
        pending_crop_selection.pop(user_id, None)

    @bot.message_handler(func=lambda message: message.text == "Отмена ❌")
    def handle_cancel(message):
        user_id = message.from_user.id
        if user_id in user_states:
            logger.info(f"❌ Пользователь {user_id} отменил операцию")
            user_states[user_id] = None
        pending_crop_selection.pop(user_id, None)
        bot.send_message(message.chat.id, "Операция отменена.", reply_markup=create_main_keyboard(user_id))

    @bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == 'waiting_for_text_coordinates')
    def handle_text_coordinates(message):
        user_id = message.from_user.id
        text = message.text.strip()

        logger.info(f"✍️ Получен текст координат от пользователя {user_id}: {text}")

        try:
            coords_pattern = r'([-+]?\d+\.?\d*)[,\s]+([-+]?\d+\.?\d*)'
            match = re.search(coords_pattern, text)

            if match:
                lat = float(match.group(1))
                lon = float(match.group(2))

                if not (-90 <= lat <= 90):
                    raise ValueError(f"Широта должна быть от -90 до 90, получено: {lat}")
                if not (-180 <= lon <= 180):
                    raise ValueError(f"Долгота должна быть от -180 до 180, получено: {lon}")

                logger.info(f"✅ Координаты распознаны: {lat}, {lon}")

                username = message.from_user.username
                first_name = message.from_user.first_name
                save_coordinates(user_id, lat, lon, username=username, first_name=first_name)

                user_states[user_id] = None

                bot.send_message(
                    message.chat.id,
                    f"✅ Координаты сохранены:\nШирота: {lat}\nДолгота: {lon}\n",
                    reply_markup=create_main_keyboard(user_id)
                )

                bot.send_location(message.chat.id, lat, lon)

                address = get_address(lat, lon)
                bot.send_message(message.chat.id, f"Примерный адрес: {address}")

                # Переходим к выбору культуры
                _send_crop_selection_or_run(bot, message.chat.id, user_id, lat, lon)

            else:
                raise ValueError("Не удалось распознать формат координат")

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга координат: {e}")
            bot.send_message(
                message.chat.id,
                f"❌ Ошибка: {str(e)}\n\nПопробуйте еще раз в формате:\n<code>55.7558, 37.6173</code>",
                parse_mode='HTML'
            )
