"""
RAG-движок для агрометеорологической литературы.
Использует ChromaDB + sentence-transformers (мультиязычная модель, без OpenAI).

Пример использования:
    from src.knowledge.rag_engine import get_rag_engine
    rag = get_rag_engine()
    print(rag.format_for_bot("водопотребление пшеницы"))
"""
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_LITERATURE_DIR = Path(__file__).parent.parent.parent / "data" / "literature"
DEFAULT_CHROMA_DIR = Path(__file__).parent.parent.parent / "data" / "chroma_db"


class AgroRAGEngine:
    """
    RAG-движок для поиска по агрометеорологической литературе.

    Workflow:
        1. Индексация: python -m src.knowledge.indexer
        2. Поиск: rag.search("сумма активных температур кукурузы")
        3. В боте: rag.format_for_bot(query)
        4. Для LLM: rag.get_context_for_llm(query)
    """

    def __init__(
        self,
        literature_dir: str = None,
        chroma_dir: str = None,
        collection_name: str = "agro_literature",
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
    ):
        self.literature_dir = Path(literature_dir) if literature_dir else DEFAULT_LITERATURE_DIR
        self.chroma_dir = Path(chroma_dir) if chroma_dir else DEFAULT_CHROMA_DIR
        self.collection_name = collection_name
        self.model_name = model_name
        self._collection = None
        self._embedding_fn = None
        self._is_ready = False

    def _init_components(self):
        """Ленивая инициализация — только при первом запросе."""
        if self._is_ready:
            return
        try:
            import chromadb
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

            self._embedding_fn = SentenceTransformerEmbeddingFunction(
                model_name=self.model_name
            )
            self.chroma_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.chroma_dir))
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self._embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
            self._is_ready = True
            logger.info(
                f"RAG Engine инициализирован. Фрагментов в базе: {self._collection.count()}"
            )
        except ImportError as e:
            logger.error(
                f"Не установлены зависимости RAG: {e}. "
                "Выполните: pip install chromadb sentence-transformers pypdf"
            )
            raise

    def is_available(self) -> bool:
        """Возвращает True если база проиндексирована и содержит документы."""
        try:
            self._init_components()
            return self._collection.count() > 0
        except Exception:
            return False

    def search(self, query: str, n_results: int = 3) -> List[dict]:
        """
        Семантический поиск по базе знаний.

        Args:
            query: запрос на русском или английском
            n_results: количество возвращаемых фрагментов

        Returns:
            Список словарей: {text, source, page, distance}
            distance — косинусное расстояние (0=идеальное совпадение, 1=нет)
        """
        self._init_components()
        count = self._collection.count()
        if count == 0:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
        )
        output = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append(
                {
                    "text": doc,
                    "source": meta.get("source", "неизвестно"),
                    "page": meta.get("page", "?"),
                    "distance": round(dist, 3),
                }
            )
        return output

    def format_for_bot(self, query: str, n_results: int = 3) -> str:
        """
        Форматирует результаты поиска для Telegram (HTML).
        Готово к прямой отправке через bot.send_message(..., parse_mode='HTML').
        """
        try:
            results = self.search(query, n_results)
            if not results:
                return (
                    "📚 <b>База знаний пуста.</b>\n"
                    "Добавьте PDF/TXT в <code>data/literature/</code> и запустите:\n"
                    "<code>python -m src.knowledge.indexer</code>"
                )
            lines = [f"📚 <b>Из научной литературы по запросу:</b> <i>{query}</i>\n"]
            for i, r in enumerate(results, 1):
                text = r["text"][:450].strip()
                if len(r["text"]) > 450:
                    text += "\u2026"
                lines.append(
                    f"<b>[{i}]</b> {text}\n"
                    f"\u2714 <i>{r['source']}, стр. {r['page']}</i>\n"
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Ошибка RAG поиска: {e}", exc_info=True)
            return f"\u274c Ошибка базы знаний: {e}"

    def get_context_for_llm(self, query: str, n_results: int = 5) -> str:
        """
        Возвращает блок контекста для передачи в LLM (Claude/Gemini/GPT).

        Использование:
            context = rag.get_context_for_llm("засухоустойчивость сортов пшеницы")
            prompt = f"{context}\n\nВопрос агронома: {user_question}"
        """
        results = self.search(query, n_results)
        if not results:
            return ""
        parts = ["=== КОНТЕКСТ ИЗ НАУЧНОЙ ЛИТЕРАТУРЫ ==="]
        for r in results:
            parts.append(f"[Источник: {r['source']}, стр. {r['page']}]\n{r['text']}")
        parts.append("=== КОНЕЦ КОНТЕКСТА ===")
        return "\n\n".join(parts)


_rag_engine: Optional[AgroRAGEngine] = None


def get_rag_engine() -> AgroRAGEngine:
    """Возвращает глобальный singleton RAG-движка."""
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = AgroRAGEngine()
    return _rag_engine
