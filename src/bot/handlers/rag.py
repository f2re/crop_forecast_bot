from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.agro.indices import compute_all_indices, format_indices_for_rag
from src.api.open_meteo import OpenMeteoError, fetch_agro_data
from src.bot.keyboards import get_rag_keyboard
from src.database.crud import get_user
from src.knowledge.llm_advisor import get_advisor
from src.knowledge.rag_engine import get_rag_engine

logger = logging.getLogger(__name__)
router = Router(name="rag")


class RagStates(StatesGroup):
    waiting_for_question = State()


@router.callback_query(F.data == "agro_advisor")
async def start_rag_session(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    rag = get_rag_engine()
    if not rag.is_available():
        await callback.message.answer(
            "📚 <b>База знаний пока пуста.</b>\n\n"
            "Ответы без проверяемых источников не генерируются."
        )
        return
    await state.set_state(RagStates.waiting_for_question)
    await callback.message.answer(
        "🤖 <b>Агрономический советник</b>\n\n"
        "Задайте вопрос по агрономии или агрометеорологии. "
        "Ответ будет основан на проиндексированных источниках.",
        reply_markup=get_rag_keyboard(),
    )


@router.callback_query(F.data == "cancel_rag")
async def cancel_rag_session(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.edit_text("Сессия агросоветника завершена.")


@router.message(StateFilter(RagStates.waiting_for_question))
async def handle_rag_question(message: Message, state: FSMContext, session) -> None:
    question = (message.text or "").strip()
    if len(question) < 5:
        await message.answer("Уточните вопрос: требуется не менее пяти символов.")
        return

    progress = await message.answer("🔍 Ищу в научной литературе…")
    try:
        rag = get_rag_engine()
        rag_context = rag.get_context_for_llm(question, n_results=4)
        agro_context = None
        user = await get_user(session, message.from_user.id)
        if user and user.latitude is not None and user.longitude is not None:
            try:
                weather = await fetch_agro_data(user.latitude, user.longitude)
                indices = compute_all_indices(
                    weather.daily,
                    user.selected_crop or "wheat",
                    utc_offset_seconds=weather.meta.utc_offset_seconds,
                )
                agro_context = format_indices_for_rag(
                    indices,
                    user.selected_crop or "wheat",
                )
            except OpenMeteoError as exc:
                logger.warning("Weather context unavailable for RAG: %s", exc)

        await progress.edit_text("🧠 Формирую ответ…")
        answer = await get_advisor().answer(
            user_question=question,
            rag_context=rag_context,
            agro_context=agro_context,
        )
        sources = rag.format_for_bot(question, n_results=2)
        await progress.edit_text(
            f"🤖 <b>Ответ агросоветника</b>\n\n{answer}\n\n"
            f"───────────────────\n{sources}"
        )
    except Exception:
        logger.exception("RAG request failed")
        await progress.edit_text("Не удалось обработать запрос. Повторите позже.")
    finally:
        await state.clear()
