"""
Хэндлер агрономического советника (RAG + LLM).
Aiogram 3.x Router.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter

from src.knowledge.rag_engine import get_rag_engine
from src.knowledge.llm_advisor import get_advisor
from src.database.crud import get_user
from src.api.open_meteo import fetch_agro_data
from src.agro.indices import compute_all_indices, format_indices_for_rag
from src.bot.keyboards import get_rag_keyboard

logger = logging.getLogger(__name__)
router = Router()


class RagStates(StatesGroup):
    waiting_for_question = State()


@router.callback_query(F.data == "agro_advisor")
async def start_rag_session(callback: CallbackQuery, state: FSMContext):
    """Пользователь нажал кнопку 'Агросоветник 🤖'."""
    await callback.answer()
    
    rag = get_rag_engine()
    if not rag.is_available():
        await callback.message.answer(
            "📚 <b>База знаний пока пуста.</b>\n\n"
            "Администратор добавит документы в ближайшее время.\n"
            "Попробуйте позже.",
            parse_mode="HTML",
        )
        return
    
    await state.set_state(RagStates.waiting_for_question)
    await callback.message.answer(
        "🤖 <b>Агрономический советник</b>\n\n"
        "Задайте вопрос по агрономии, защите растений или агрометеорологии.\n\n"
        "<i>Примеры:</i>\n"
        "• Какова норма водопотребления пшеницы?\n"
        "• Симптомы дефицита азота у кукурузы\n"
        "• При каком ГТК начинается почвенная засуха?\n\n"
        "✏️ <b>Введите ваш вопрос:</b>",
        parse_mode="HTML",
        reply_markup=get_rag_keyboard(),
    )


@router.callback_query(F.data == "cancel_rag")
async def cancel_rag_session(callback: CallbackQuery, state: FSMContext):
    """Отмена сессии советника."""
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.edit_text("🤖 Сессия агросоветника завершена.")


@router.message(StateFilter(RagStates.waiting_for_question))
async def handle_rag_question(message: Message, state: FSMContext, session):
    """Обработка вопроса пользователя."""
    user_question = message.text.strip()
    
    if len(user_question) < 5:
        await message.answer("⚠️ Слишком короткий вопрос. Уточните, пожалуйста.")
        return
    
    # Сообщение о процессе (пользователь видит, что бот думает)
    thinking_msg = await message.answer("🔍 Ищу в научной литературе...")
    
    try:
        # 1. Семантический поиск по базе знаний
        rag = get_rag_engine()
        rag_context = rag.get_context_for_llm(user_question, n_results=4)
        
        # 2. Получить агроданные пользователя (если есть координаты)
        agro_context = None
        user = await get_user(session, message.from_user.id)
        if user and user.latitude and user.longitude:
            try:
                df_daily, _ = await fetch_agro_data(user.latitude, user.longitude)
                if df_daily is not None:
                    indices = compute_all_indices(df_daily, user.selected_crop or "wheat")
                    # Форматируем краткую сводку для LLM
                    agro_context = format_indices_for_rag(indices, user.selected_crop)
            except Exception as e:
                logger.warning(f"Не удалось получить агроданные для RAG: {e}")
        
        # 3. Вызов LLM
        await thinking_msg.edit_text("🧠 Формирую ответ...")
        advisor = get_advisor()
        llm_answer = await advisor.answer(
            user_question=user_question,
            rag_context=rag_context,
            agro_context=agro_context,
        )
        
        # 4. Форматирование финального ответа
        sources_block = rag.format_for_bot(user_question, n_results=2)
        final_text = (
            f"🤖 <b>Ответ агросоветника:</b>\n\n"
            f"{llm_answer}\n\n"
            f"───────────────────\n"
            f"{sources_block}"
        )
        
        await thinking_msg.delete()
        await message.answer(final_text, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"RAG handler error: {e}", exc_info=True)
        await thinking_msg.edit_text(
            "❌ Произошла ошибка при обработке запроса. Попробуйте позже."
        )
    
    finally:
        # Сбросить состояние — готовы к новому вопросу
        await state.clear()
