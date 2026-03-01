"""
Индексация агрометеорологической литературы в ChromaDB.

Форматы: PDF, TXT, MD
Чанки: 800 символов с перекрытием 150

Команды:
    python -m src.knowledge.indexer              # индексировать data/literature/
    python -m src.knowledge.indexer --reset      # сбросить и переиндексировать
    python -m src.knowledge.indexer --info       # показать статистику базы
    python -m src.knowledge.indexer --dir /path  # указать другую папку
"""
import argparse
import hashlib
import logging
import sys
from pathlib import Path
from typing import List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_LITERATURE_DIR = Path(__file__).parent.parent.parent / "data" / "literature"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Разбивает текст на перекрывающиеся фрагменты."""
    chunks, start = [], 0
    while start < len(text):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def extract_pdf(file_path: Path) -> List[Tuple[str, int]]:
    """Извлекает текст из PDF постранично."""
    try:
        import pypdf

        pages = []
        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for num, page in enumerate(reader.pages, 1):
                text = page.extract_text()
                if text and text.strip():
                    pages.append((text, num))
        return pages
    except Exception as e:
        logger.error(f"Ошибка чтения PDF {file_path.name}: {e}")
        return []


def extract_txt(file_path: Path) -> List[Tuple[str, int]]:
    """Читает TXT/MD-файл целиком."""
    try:
        return [(file_path.read_text(encoding="utf-8", errors="ignore"), 1)]
    except Exception as e:
        logger.error(f"Ошибка чтения {file_path.name}: {e}")
        return []


def index_documents(literature_dir: Path = DEFAULT_LITERATURE_DIR, reset: bool = False):
    """Основная функция индексации: читает файлы, создаёт чанки, записывает в ChromaDB."""
    from src.knowledge.rag_engine import AgroRAGEngine

    supported = {".pdf", ".txt", ".md"}
    files = [f for f in literature_dir.rglob("*") if f.suffix.lower() in supported]

    if not files:
        logger.warning(f"Нет файлов для индексации в {literature_dir}")
        logger.info(
            "Положите PDF/TXT/MD в папку data/literature/ и запустите:\n"
            "  python -m src.knowledge.indexer"
        )
        return

    logger.info(f"Найдено файлов: {len(files)}")
    engine = AgroRAGEngine()
    engine._init_components()
    col = engine._collection

    if reset:
        ids = col.get()["ids"]
        if ids:
            col.delete(ids=ids)
        logger.info(f"База очищена ({len(ids)} записей удалено).")

    existing_hashes: set = set()
    if col.count() > 0:
        existing_hashes = {
            m.get("file_hash", "") for m in col.get()["metadatas"] if m
        }

    for file_path in files:
        fhash = hashlib.md5(file_path.read_bytes()).hexdigest()
        if fhash in existing_hashes:
            logger.info(f"\u23ed  Пропуск (уже в базе): {file_path.name}")
            continue

        logger.info(f"\U0001f4c4 Обработка: {file_path.name}")
        pages = (
            extract_pdf(file_path)
            if file_path.suffix.lower() == ".pdf"
            else extract_txt(file_path)
        )
        if not pages:
            logger.warning(f"  Пустой файл или не удалось извлечь текст: {file_path.name}")
            continue

        docs, metas, ids = [], [], []
        for text, page_num in pages:
            for j, chunk in enumerate(chunk_text(text)):
                docs.append(chunk)
                metas.append(
                    {
                        "source": file_path.name,
                        "page": str(page_num),
                        "file_hash": fhash,
                        "file_path": str(file_path),
                    }
                )
                ids.append(f"{fhash}_{page_num}_{j}")

        if docs:
            batch = 100
            for i in range(0, len(docs), batch):
                col.add(
                    documents=docs[i : i + batch],
                    metadatas=metas[i : i + batch],
                    ids=ids[i : i + batch],
                )
            logger.info(f"  \u2705 {len(docs)} фрагментов из {file_path.name}")

    logger.info(f"\n\u2705 Итого фрагментов в базе: {col.count()}")


def show_info():
    """Выводит статистику базы знаний."""
    from src.knowledge.rag_engine import AgroRAGEngine

    engine = AgroRAGEngine()
    try:
        engine._init_components()
    except Exception as e:
        print(f"Ошибка инициализации: {e}")
        return
    col = engine._collection
    count = col.count()
    if count == 0:
        print("База пуста. Запустите: python -m src.knowledge.indexer")
        return
    sources = {m.get("source", "?") for m in col.get()["metadatas"] if m}
    print(f"\U0001f4da Фрагментов в базе: {count}")
    print(f"\U0001f4c4 Источников: {len(sources)}")
    for s in sorted(sources):
        print(f"   \u2022 {s}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Индексация агрометеорологической литературы в ChromaDB"
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=str(DEFAULT_LITERATURE_DIR),
        help="Папка с литературой (по умолчанию: data/literature/)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Сбросить базу перед индексацией",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Показать статистику базы без индексации",
    )
    args = parser.parse_args()

    if args.info:
        show_info()
        sys.exit(0)

    lit_dir = Path(args.dir)
    lit_dir.mkdir(parents=True, exist_ok=True)
    index_documents(lit_dir, reset=args.reset)
