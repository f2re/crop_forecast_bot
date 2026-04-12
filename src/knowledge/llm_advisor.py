"""
LLM-надстройка над RAG для агрономических консультаций.
Поддерживает: OpenAI, Together.ai, Groq (OpenAI-совместимый API),
              Anthropic Claude, локальный Ollama.
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — агрометеорологический советник-агроном.
Отвечай на вопросы фермеров кратко, конкретно и практично.
Используй ТОЛЬКО данные из предоставленного контекста.
Если в контексте нет ответа — честно скажи об этом.
Упоминай конкретные пороговые значения, сроки, культуры.
Отвечай на русском языке. Максимум 3–5 предложений."""


class LLMAdvisor:
    """
    Обёртка для вызова LLM с RAG-контекстом.
    
    Порядок приоритета провайдеров:
        1. Groq (бесплатный tier, быстрый, llama-3-70b)
        2. Together.ai (дешёвый, mixtral)
        3. OpenAI (платный)
        4. Ollama (локальный, без интернета)
    """

    def __init__(self, provider: str = "groq"):
        self.provider = provider
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        
        if self.provider in ("groq", "together", "openai"):
            from openai import AsyncOpenAI
            base_urls = {
                "groq": "https://api.groq.com/openai/v1",
                "together": "https://api.together.xyz/v1",
                "openai": "https://api.openai.com/v1",
            }
            api_keys = {
                "groq": os.getenv("GROQ_API_KEY"),
                "together": os.getenv("TOGETHER_API_KEY"),
                "openai": os.getenv("OPENAI_API_KEY"),
            }
            self._client = AsyncOpenAI(
                base_url=base_urls[self.provider],
                api_key=api_keys[self.provider],
            )
        elif self.provider == "ollama":
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
            )
        return self._client

    def _get_model(self) -> str:
        models = {
            "groq": "llama-3.3-70b-versatile",      # Рекомендуется для MVP
            "together": "mistralai/Mixtral-8x7B-Instruct-v0.1",
            "openai": "gpt-4o-mini",
            "ollama": "llama3.2:3b",                 # Локальная модель
        }
        return models.get(self.provider, "llama-3.3-70b-versatile")

    async def answer(
        self,
        user_question: str,
        rag_context: str,
        agro_context: Optional[str] = None,
        max_tokens: int = 400,
    ) -> str:
        """
        Получить ответ LLM с RAG-контекстом.

        Args:
            user_question: вопрос фермера
            rag_context: результат rag.get_context_for_llm()
            agro_context: текущие агроиндексы (ГТК, ГДД, заморозки и т.д.)
            max_tokens: максимум токенов в ответе

        Returns:
            Текстовый ответ (русский)
        """
        try:
            client = self._get_client()
            
            # Формирование промпта
            parts = []
            if rag_context:
                parts.append(rag_context)
            if agro_context:
                parts.append(f"=== ТЕКУЩИЕ АГРОМЕТЕОДАННЫЕ ===\n{agro_context}\n=== КОНЕЦ ДАННЫХ ===")
            
            full_context = "\n\n".join(parts) if parts else ""
            user_message = f"{full_context}\n\nВопрос агронома: {user_question}" if full_context else user_question
            
            response = await client.chat.completions.create(
                model=self._get_model(),
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=max_tokens,
                temperature=0.3,  # Низкая температура = фактологичность
            )
            return response.choices[0].message.content.strip()
        
        except Exception as e:
            logger.error(f"LLM ошибка ({self.provider}): {e}", exc_info=True)
            return f"⚠️ Сервис консультаций временно недоступен. Попробуйте позже."


# Singleton
_advisor: Optional[LLMAdvisor] = None

def get_advisor() -> LLMAdvisor:
    global _advisor
    if _advisor is None:
        provider = os.getenv("LLM_PROVIDER", "groq")
        _advisor = LLMAdvisor(provider=provider)
    return _advisor
