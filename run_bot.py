import telebot
import time
import socket
import requests
import asyncio
import logging
from config.settings import TELEGRAM_BOT_TOKEN, get_database_url
from src.bot.handlers import register_handlers
from src.database import init_db

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def check_network_connectivity():
    """Проверяет доступность сети перед запуском бота."""
    max_retries = 5
    retry_delay = 2

    for attempt in range(1, max_retries + 1):
        try:
            # Проверка DNS
            socket.gethostbyname('api.telegram.org')

            # Проверка HTTP подключения
            response = requests.get('https://api.telegram.org', timeout=5)
            print(f"✓ Сеть доступна (попытка {attempt}/{max_retries})", flush=True)
            return True
        except Exception as e:
            print(f"⚠ Сеть недоступна (попытка {attempt}/{max_retries}): {e}", flush=True)
            if attempt < max_retries:
                print(f"  Повторная попытка через {retry_delay} секунд...", flush=True)
                time.sleep(retry_delay)
                retry_delay *= 2  # Экспоненциальная задержка
            else:
                print("✗ Не удалось установить сетевое подключение после всех попыток", flush=True)
                return False


def init_database():
    """Инициализирует базу данных."""
    try:
        database_url = get_database_url()
        logger.info(f"🔧 Инициализация базы данных...")
        db = init_db(database_url)

        # Create tables if they don't exist
        async def create_tables():
            await db.create_tables()
            logger.info("✓ Таблицы базы данных проверены/созданы")

        asyncio.run(create_tables())
        logger.info("✓ База данных инициализирована успешно")
        return True
    except Exception as e:
        logger.error(f"✗ Ошибка при инициализации базы данных: {e}", exc_info=True)
        return False


def start_bot():
    """Инициализирует и запускает бота."""
    if not TELEGRAM_BOT_TOKEN:
        print("Ошибка: Токен для Telegram не найден. Проверьте ваш .env файл.", flush=True)
        return

    # Initialize database
    logger.info("Инициализация базы данных...")
    if not init_database():
        logger.error("Не удалось инициализировать базу данных. Проверьте настройки DATABASE_URL.")
        time.sleep(10)
        return

    # Проверка сети перед запуском
    print("Проверка сетевого подключения...", flush=True)
    if not check_network_connectivity():
        print("Ошибка: Не могу подключиться к Telegram API. Проверьте сетевые настройки.", flush=True)
        time.sleep(10)  # Пауза перед выходом, чтобы увидеть ошибку в логах
        return

    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
    register_handlers(bot)

    print("Бот запущен и подключен к Telegram API...", flush=True)

    # Запуск с retry логикой
    retry_count = 0
    max_retries = 10

    while retry_count < max_retries:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=25, skip_pending=True)
        except requests.exceptions.ReadTimeout:
            print("⚠ Таймаут при чтении от Telegram API, переподключение...", flush=True)
            time.sleep(5)
            retry_count += 1
        except requests.exceptions.ConnectionError as e:
            print(f"⚠ Ошибка подключения к Telegram API: {e}", flush=True)
            retry_count += 1
            wait_time = min(60, 5 * (2 ** retry_count))  # Экспоненциальная задержка, макс 60 сек
            print(f"  Повторная попытка через {wait_time} секунд (попытка {retry_count}/{max_retries})...", flush=True)
            time.sleep(wait_time)
        except KeyboardInterrupt:
            print("\nБот остановлен пользователем.", flush=True)
            break
        except Exception as e:
            print(f"✗ Произошла ошибка: {e}", flush=True)
            retry_count += 1
            if retry_count < max_retries:
                print(f"  Перезапуск через 10 секунд...", flush=True)
                time.sleep(10)
            else:
                print(f"✗ Превышено максимальное количество попыток ({max_retries}). Бот остановлен.", flush=True)
                break


if __name__ == "__main__":
    start_bot()
