import telebot
from config.settings import TELEGRAM_BOT_TOKEN
from src.bot.handlers import register_handlers

# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Регистрация всех обработчиков
register_handlers(bot)

# Запуск бота
if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()
