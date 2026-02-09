"""
RAG dokümanlarını yeniden indeksleme script'i.

Kullanım:
    python -m rag.build_index
ya da
    python rag/build_index.py
"""
from pathlib import Path
import structlog

from config.settings import settings
from rag.vector_store import DepartmentVectorStore

logger = structlog.get_logger()


def _load_department_docs(dept_dir: Path):
    """Departman klasöründeki .txt dosyalarını okur, paragraflara böler."""
    documents = []
    for file_path in dept_dir.glob("*.txt"):
        try:
            content = file_path.read_text(encoding="utf-8")
            # Boş satırlara göre paragrafa ayır, temizle
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            documents.extend(paragraphs)
        except Exception as e:
            logger.warning("doc_read_error", file=str(file_path), error=str(e))
    return documents


def rebuild():
    data_dir = Path(settings.data_dir)
    chroma_dir = Path(settings.chroma_dir)

    if not data_dir.exists():
        logger.error("data_dir_not_found", path=str(data_dir))
        return

    store = DepartmentVectorStore(str(chroma_dir))

    for dept_dir in data_dir.iterdir():
        if not dept_dir.is_dir():
            continue
        department = dept_dir.name
        docs = _load_department_docs(dept_dir)
        logger.info("reindex_department", department=department, doc_count=len(docs))

        # Eski collection'ı sil ve yeniden yükle
        dept_store = store.get_store(department)
        dept_store.delete_collection()
        if docs:
            store.add_department_documents(department, docs)

    logger.info("reindex_completed", base_dir=str(chroma_dir))


if __name__ == "__main__":
    rebuild()

