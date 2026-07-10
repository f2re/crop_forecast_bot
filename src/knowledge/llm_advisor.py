from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — агрометеорологический справочный помощник.
Используй только факты из предоставленного контекста и явно названных источников.
Если контекста недостаточно, скажи об этом. Не придумывай нормы, дозы,
пороговые значения, прогноз урожайности или данные поля. Отвечай по-русски,
кратко и отделяй факт источника от оперативного расчёта бота."""

_PROVIDER_CONFIG: dict[str, tuple[str, str, str]] = {
    "groq": (
        "https://api.groq.com/openai/v1",
        "GROQ_API_KEY",
        "llama-3.3-70b-versatile",
    ),
    "together": (
        "https://api.together.xyz/v1",
        "TOGETHER_API_KEY",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
    ),
    "openai": (
        "https://api.openai.com/v1",
        "OPENAI_API_KEY",
        "gpt-4o-mini",
    ),
}


class LLMAdvisor:
    """Optional OpenAI-compatible LLM adapter over retrieved source context."""

    def __init__(self, provider: str = "groq") -> None:
        self.provider = provider.strip().lower()
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        from openai import AsyncOpenAI

        if self.provider == "ollama":
            self._client = AsyncOpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
            )
            return self._client

        try:
            base_url, key_name, _ = _PROVIDER_CONFIG[self.provider]
        except KeyError as exc:
            supported = ", ".join((*_PROVIDER_CONFIG, "ollama"))
            raise RuntimeError(
                f"Unsupported LLM_PROVIDER={self.provider!r}; supported: {supported}"
            ) from exc

        api_key = os.getenv(key_name, "").strip()
        if not api_key:
            raise RuntimeError(f"{key_name} is required for provider {self.provider}")
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        return self._client

    def _get_model(self) -> str:
        if self.provider == "ollama":
            return os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        try:
            return _PROVIDER_CONFIG[self.provider][2]
        except KeyError as exc:
            raise RuntimeError(f"Unsupported LLM provider: {self.provider}") from exc

    async def answer(
        self,
        user_question: str,
        rag_context: str,
        agro_context: str | None = None,
        max_tokens: int = 400,
    ) -> str:
        if not rag_context.strip():
            return "В базе знаний не найден проверяемый контекст для ответа."

        parts = [rag_context]
        if agro_context:
            parts.append(
                "=== ОПЕРАТИВНЫЙ РАСЧЁТ БОТА ===\n"
                f"{agro_context}\n"
                "=== КОНЕЦ ОПЕРАТИВНОГО РАСЧЁТА ==="
            )
        context = "\n\n".join(parts)
        user_message = f"{context}\n\nВопрос пользователя: {user_question}"

        try:
            response = await self._get_client().chat.completions.create(
                model=self._get_model(),
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            )
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("LLM returned an empty response")
            return content.strip()
        except Exception as exc:
            logger.exception("LLM provider %s failed: %s", self.provider, exc)
            return "Сервис консультаций сейчас недоступен. Найденные источники показаны ниже."


_advisor: LLMAdvisor | None = None


def get_advisor() -> LLMAdvisor:
    global _advisor
    if _advisor is None:
        _advisor = LLMAdvisor(provider=os.getenv("LLM_PROVIDER", "groq"))
    return _advisor
