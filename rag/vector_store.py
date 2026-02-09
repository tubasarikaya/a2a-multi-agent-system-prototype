"""
Vector Store - ChromaDB ile semantik arama.

Her departman için ayrı collection oluşturulur.
"""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import structlog

logger = structlog.get_logger()


class VectorStore:
    """
    ChromaDB tabanlı vektör veritabanı.
    Semantik arama için embedding'ler saklar.
    """

    def __init__(
        self,
        collection_name: str,
        persist_directory: Optional[str] = None,
        embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    ):
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.embedding_model = embedding_model

        self._client = None
        self._collection = None
        self._embedding_function = None

    def _get_embedding_function(self):
        """Embedding fonksiyonunu lazy load eder."""
        if self._embedding_function is None:
            try:
                from chromadb.utils import embedding_functions
                self._embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=self.embedding_model
                )
            except Exception as e:
                logger.warning("embedding_function_fallback", error=str(e))
                # Fallback: default embedding
                self._embedding_function = None
        return self._embedding_function

    def _get_client(self):
        """ChromaDB client'ı lazy load eder."""
        if self._client is None:
            import chromadb
            from chromadb.config import Settings

            if self.persist_directory:
                os.makedirs(self.persist_directory, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=self.persist_directory,
                    settings=Settings(anonymized_telemetry=False)
                )
            else:
                self._client = chromadb.Client(
                    settings=Settings(anonymized_telemetry=False)
                )

        return self._client

    def _get_collection(self):
        """Collection'ı lazy load eder."""
        if self._collection is None:
            client = self._get_client()
            ef = self._get_embedding_function()

            kwargs = {"name": self.collection_name}
            if ef:
                kwargs["embedding_function"] = ef

            self._collection = client.get_or_create_collection(**kwargs)

        return self._collection

    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ):
        """Dokümanları vektör veritabanına ekler."""
        collection = self._get_collection()

        if ids is None:
            ids = [f"doc_{i}" for i in range(len(documents))]

        if metadatas is None:
            metadatas = [{}] * len(documents)

        # ChromaDB metadata kısıtlaması: sadece str, int, float
        clean_metadatas = []
        for meta in metadatas:
            clean_meta = {}
            for k, v in meta.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_meta[k] = v
                else:
                    clean_meta[k] = str(v)
            clean_metadatas.append(clean_meta)

        collection.add(
            documents=documents,
            metadatas=clean_metadatas,
            ids=ids
        )

        logger.info(
            "documents_added",
            collection=self.collection_name,
            count=len(documents)
        )

    def search(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Semantik arama yapar.
        Returns: [(document, distance, metadata), ...]
        """
        collection = self._get_collection()

        try:
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where
            )

            output = []
            if results["documents"] and results["documents"][0]:
                documents = results["documents"][0]
                distances = results["distances"][0] if results["distances"] else [0] * len(documents)
                metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(documents)

                for doc, dist, meta in zip(documents, distances, metadatas):
                    output.append((doc, dist, meta))

            logger.debug(
                "search_completed",
                collection=self.collection_name,
                query=query[:50],
                results=len(output)
            )

            return output

        except Exception as e:
            logger.error("search_error", collection=self.collection_name, error=str(e))
            return []

    def delete_collection(self):
        """Collection'ı siler."""
        client = self._get_client()
        try:
            client.delete_collection(self.collection_name)
            self._collection = None
            logger.info("collection_deleted", collection=self.collection_name)
        except Exception as e:
            logger.error("delete_collection_error", error=str(e))

    def get_count(self) -> int:
        """Collection'daki doküman sayısını döndürür."""
        collection = self._get_collection()
        return collection.count()


class DepartmentVectorStore:
    """
    Departman bazlı vektör veritabanı yöneticisi.
    Her departman için ayrı collection oluşturur.
    """

    def __init__(self, base_directory: str):
        self.base_directory = Path(base_directory)
        self._stores: Dict[str, VectorStore] = {}

    def get_store(self, department: str) -> VectorStore:
        """Departman için vektör veritabanını döndürür."""
        if department not in self._stores:
            persist_dir = str(self.base_directory / department)
            self._stores[department] = VectorStore(
                collection_name=f"{department}_docs",
                persist_directory=persist_dir
            )
        return self._stores[department]

    def add_department_documents(
        self,
        department: str,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ):
        """Departmana ait dokümanları ekler."""
        store = self.get_store(department)

        # Metadata'ya departman bilgisi ekle
        if metadatas is None:
            metadatas = [{"department": department}] * len(documents)
        else:
            for meta in metadatas:
                meta["department"] = department

        store.add_documents(documents, metadatas, ids)

    def search_department(
        self,
        department: str,
        query: str,
        n_results: int = 5
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Belirli bir departmanda arama yapar."""
        store = self.get_store(department)
        return store.search(query, n_results)

    def search_all(
        self,
        query: str,
        n_results_per_department: int = 3
    ) -> Dict[str, List[Tuple[str, float, Dict[str, Any]]]]:
        """Tüm departmanlarda arama yapar."""
        results = {}
        for dept, store in self._stores.items():
            dept_results = store.search(query, n_results_per_department)
            if dept_results:
                results[dept] = dept_results
        return results

    def load_from_directory(self, data_directory: str):
        """
        Dizinden dokümanları yükler.
        Her alt dizin bir departman olarak kabul edilir.
        """
        data_path = Path(data_directory)

        if not data_path.exists():
            logger.warning("data_directory_not_found", path=data_directory)
            return

        for dept_dir in data_path.iterdir():
            if dept_dir.is_dir():
                department = dept_dir.name
                documents = []
                metadatas = []
                ids = []

                for file_path in dept_dir.glob("*.txt"):
                    try:
                        content = file_path.read_text(encoding="utf-8")

                        # Paragrafları ayır
                        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

                        for i, para in enumerate(paragraphs):
                            documents.append(para)
                            metadatas.append({
                                "source": file_path.name,
                                "paragraph_index": i
                            })
                            ids.append(f"{department}_{file_path.stem}_{i}")

                    except Exception as e:
                        logger.error(
                            "file_load_error",
                            file=str(file_path),
                            error=str(e)
                        )

                if documents:
                    self.add_department_documents(
                        department=department,
                        documents=documents,
                        metadatas=metadatas,
                        ids=ids
                    )
                    logger.info(
                        "department_documents_loaded",
                        department=department,
                        count=len(documents)
                    )
