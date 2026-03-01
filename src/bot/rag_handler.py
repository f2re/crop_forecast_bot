"""
Обработчики Telegram-бота для RAG-системы знаний.

Подключение в handlers.py (добавить 2 строки):
    from src.bot.rag_handler import register_rag_handlers
    # в конце функции register_handlers(bot):
    register_rag_handlers(bot)

Новые возможности:
    - Кнопка "Справочник \U0001f4da" в главном меню
    - Команда /literature <запрос>
    - Интерактивный поиск с ожиданием текста
"""
import logging
from src.bot.keyboards import create_main_keyboard
from src.knowledge.rag_engine import get_rag_engine

logger = logging.getLogger(__name__)

# Локальные состояния пользователей для RAG-диалога
_rag_states: dict = {}


def register_rag_handlers(bot):
    """
    Регистрирует все обработчики RAG-системы в экземпляре бота.
    Вызывать в конце register_handlers(bot) в handlers.py.
    """

    @bot.message_handler(func=lambda m: m.text == "\U0001f4da Справочник")
    @bot.message_handler(func=lambda m: m.text == "Справочник \U0001f4da")
    def handle_literature_button(message):
        """Нажатие кнопки Справочник — переходим в режим ввода запроса."""
        user_id = message.from_user.id
        _rag_states[user_id] = "waiting_for_lit_query"
        bot.send_message(
            message.chat.id,
            "\U0001f4da <b>Поиск по агрометеорологической литературе</b>\n\n"
            "Введите запрос, например:\n"
            "\u2022 <i>критические периоды водопотребления пшеницы</i>\n"
            "\u2022 <i>сумма активных температур кукуруза FAO 300</i>\n"
            "\u2022 <i>заморозки яровые культуры вероятность</i>\n"
            "\u2022 <i>норма осадков вегетационный период</i>",
            parse_mode="HTML",
            reply_markup=create_main_keyboard(user_id),
        )

    @bot.message_handler(commands=["literature"])
    def handle_literature_command(message):
        """Команда /literature <запрос> — прямой поиск без ожидания."""
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.send_message(
                message.chat.id,
                "\U0001f4da Использование: /literature <запрос>\n"
                "Пример: /literature сумма активных температур пшеница",
            )
            return
        _do_rag_search(bot, message, parts[1].strip())

    @bot.message_handler(
        func=lambda m: _rag_states.get(m.from_user.id) == "waiting_for_lit_query"
    )
    def handle_literature_query(message):
        """Получает текст запроса от пользователя и выполняет поиск."""
        user_id = message.from_user.id
        _rag_states.pop(user_id, None)
        _do_rag_search(bot, message, message.text.strip())


def _do_rag_search(bot, message, query: str):
    """Выполняет RAG-поиск и отправляет результат."""
    rag = get_rag_engine()
    bot.send_chat_action(message.chat.id, "typing")
    try:
        response = rag.format_for_bot(query, n_results=3)
        bot.send_message(
            message.chat.id,
            response,
            parse_mode="HTML",
            reply_markup=create_main_keyboard(message.from_user.id),
        )
    except Exception as e:
        logger.error(f"Ошибка RAG handler: {e}", exc_info=True)
        bot.send_message(
            message.chat.id,
            f"\u274c Ошибка при поиске по литературе: {e}",
            reply_markup=create_main_keyboard(message.from_user.id),
        )


def get_rag_context_for_crop(crop_name: str, climate_context: str = "") -> str:
    """
    Утилита для crop_recommender_handler.py.
    Возвращает научный контекст для культуры — можно добавить к рекомендации.

    Использование в crop_recommender_handler.py:
        from src.bot.rag_handler import get_rag_context_for_crop
        rag_ctx = get_rag_context_for_crop(crop_name, climate_context)
        if rag_ctx:
            bot.send_message(chat_id, rag_ctx, parse_mode='HTML')
    """
    rag = get_rag_engine()
    if not rag.is_available():
        return ""
    query = f"{crop_name} агрометеорология условия выращивания {climate_context}".strip()
    return rag.format_for_bot(query, n_results=2)
