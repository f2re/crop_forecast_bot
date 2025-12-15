"""
Обработчик для получения рекомендаций по культурам
Упрощенная синхронная версия с fallback на simple_recommender
"""
import logging
from datetime import datetime
from geopy.geocoders import Nominatim
from src.bot.simple_recommender import format_simple_recommendation

logger = logging.getLogger(__name__)
geolocator = Nominatim(user_agent="crop_recommendation_bot")


def handle_crop_recommendation_request(bot, message):
    """
    Главный обработчик запроса на рекомендации по культурам
    Синхронная версия с fallback режимом

    Args:
        bot: экземпляр бота
        message: сообщение от пользователя с координатами
    """
    lat = message.location.latitude
    lon = message.location.longitude
    user_id = message.from_user.id

    logger.info(f"🚀 Запуск анализа для пользователя {user_id}: {lat}, {lon}")

    try:
        # Получение адреса
        try:
            location = geolocator.reverse((lat, lon), language='ru', timeout=10)
            address = location.address if location else "Адрес не определен"
        except Exception as e:
            logger.warning(f"Не удалось получить адрес: {e}")
            address = f"Координаты: {lat:.4f}, {lon:.4f}"

        # Отправка приветственного сообщения
        bot.send_message(
            message.chat.id,
            f"🌍 Анализирую условия для вашего участка...\n"
            f"📍 {address}\n\n"
            f"⏳ Пожалуйста, подождите..."
        )

        logger.info(f"📊 Используем упрощенный режим рекомендаций (без API)")

        # Используем простой рекомендатель
        recommendation_text = format_simple_recommendation(lat, lon)

        logger.info(f"✅ Рекомендации сформированы для пользователя {user_id}")

        # Отправка рекомендаций
        bot.send_message(
            message.chat.id,
            recommendation_text
        )

        # Дополнительная информация
        bot.send_message(
            message.chat.id,
            "ℹ️ *Как улучшить точность рекомендаций:*\n\n"
            "1️⃣ Настройте Copernicus CDS API для климатических данных\n"
            "2️⃣ Настройте Google Earth Engine для спутниковых данных\n"
            "3️⃣ Настройте OpenRouter API для персонализированных советов\n\n"
            "📖 Подробности в README.md и PLATFORM_INTEGRATION.md",
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике рекомендаций: {e}", exc_info=True)

        try:
            bot.send_message(
                message.chat.id,
                f"❌ Произошла ошибка при обработке запроса:\n{str(e)}\n\n"
                "Пожалуйста, попробуйте позже или обратитесь в поддержку."
            )
        except:
            pass  # Даже отправка сообщения об ошибке не удалась
