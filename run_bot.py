import telebot
from config.settings import TELEGRAM_BOT_TOKEN
from src.bot.handlers import register_handlers

def start_bot():
    """Инициализирует и запускает бота."""
    if not TELEGRAM_BOT_TOKEN:
        print("Ошибка: Токен для Telegram не найден. Проверьте ваш .env файл.")
        return

    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
    register_handlers(bot)

    print("Бот запущен...", flush=True)
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"Произошла ошибка: {e}")

if __name__ == "__main__":
    start_bot()
