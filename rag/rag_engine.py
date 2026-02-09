"""
RAG Engine - Retrieval Augmented Generation motoru.

Vektör veritabanından ilgili dokümanları alır ve
LLM'e bağlam olarak sunar.
"""
from typing import Any, Dict, List, Optional, Tuple
import structlog

from llm.provider import LLMProvider
from llm.prompts import SystemPrompts
from .vector_store import VectorStore, DepartmentVectorStore

logger = structlog.get_logger()


class RAGEngine:
    """
    RAG motoru - arama ve yanıt üretimini birleştirir.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        vector_store: Optional[VectorStore] = None,
        department_store: Optional[DepartmentVectorStore] = None,
        n_results: int = 5,
        min_relevance_score: float = 1.5  # ChromaDB distance threshold
    ):
        self.llm = llm_provider
        self.vector_store = vector_store
        self.department_store = department_store
        self.n_results = n_results
        self.min_relevance_score = min_relevance_score

    async def query(
        self,
        question: str,
        department: Optional[str] = None,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        RAG sorgusu yapar.

        Args:
            question: Kullanıcı sorusu
            department: Belirli bir departmanda ara (opsiyonel)
            use_llm: LLM ile yanıt üretilsin mi?

        Returns:
            {
                "answer": "Üretilen yanıt",
                "sources": [{"content": "...", "metadata": {...}}],
                "department": "departman_adı"
            }
        """
        # Karmaşık sorularda daha fazla sonuç getir
        # Soru uzunluğu ve kelime sayısına göre dinamik ayarlama
        word_count = len(question.split())
        question_length = len(question)
        
        # Karmaşık soru tespiti: uzun sorular veya çoklu sorular
        is_complex = (
            word_count > 15 or  # 15+ kelime
            question_length > 100 or  # 100+ karakter
            question.count("?") > 1 or  # Çoklu soru işareti
            any(connector in question.lower() for connector in [" ve ", " ayrıca ", " hem ", " ile "])  # Bağlaçlar
        )
        
        # Karmaşık sorularda daha fazla sonuç
        dynamic_n_results = self.n_results * 2 if is_complex else self.n_results
        
        # Arama yap
        search_results = await self._search(question, department, n_results=dynamic_n_results)

        if not search_results:
            return {
                "answer": "Bu konuda ilgili bilgi bulunamadı.",
                "sources": [],
                "department": department
            }

        # Bağlamı oluştur
        context = self._build_context(search_results)
        sources = [
            {"content": doc, "metadata": meta, "score": score}
            for doc, score, meta in search_results
        ]

        if not use_llm:
            return {
                "answer": context,
                "sources": sources,
                "department": department
            }

        # LLM ile yanıt üret
        try:
            prompt = SystemPrompts.get_rag_prompt(context, question)
            answer = await self.llm.generate(prompt)

            return {
                "answer": answer,
                "sources": sources,
                "department": department
            }

        except Exception as e:
            logger.error("rag_llm_error", error=str(e))
            # Fallback: sadece bağlamı döndür
            return {
                "answer": f"Bulunan bilgiler:\n\n{context}",
                "sources": sources,
                "department": department
            }

    async def _search(
        self,
        query: str,
        department: Optional[str] = None,
        n_results: Optional[int] = None
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Vektör veritabanında arama yapar."""
        
        # n_results belirtilmediyse varsayılanı kullan
        search_n_results = n_results if n_results is not None else self.n_results

        results = []

        # Departman bazlı arama
        if department and self.department_store:
            results = self.department_store.search_department(
                department=department,
                query=query,
                n_results=search_n_results
            )

        # Genel arama
        elif self.vector_store:
            results = self.vector_store.search(
                query=query,
                n_results=search_n_results
            )

        # Tüm departmanlarda arama
        elif self.department_store:
            all_results = self.department_store.search_all(
                query=query,
                n_results_per_department=search_n_results
            )
            for dept_results in all_results.values():
                results.extend(dept_results)
            # Skora göre sırala
            results.sort(key=lambda x: x[1])
            results = results[:search_n_results]

        # Relevance threshold uygula
        filtered_results = [
            r for r in results if r[1] <= self.min_relevance_score
        ]

        logger.debug(
            "rag_search",
            query=query[:50],
            department=department,
            total_results=len(results),
            filtered_results=len(filtered_results)
        )

        return filtered_results

    def _build_context(
        self,
        search_results: List[Tuple[str, float, Dict[str, Any]]]
    ) -> str:
        """Arama sonuçlarından bağlam metni oluşturur."""
        context_parts = []

        for i, (doc, score, meta) in enumerate(search_results, 1):
            source = meta.get("source", "bilinmeyen")
            dept = meta.get("department", "")

            header = f"[Kaynak {i}"
            if dept:
                header += f" - {dept}"
            header += f" - {source}]"

            context_parts.append(f"{header}\n{doc}")

        return "\n\n".join(context_parts)

    async def query_multiple_departments(
        self,
        question: str,
        departments: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Birden fazla departmanda arama yapar.
        Her departman için ayrı sonuç döndürür.
        """
        results = {}

        for dept in departments:
            dept_result = await self.query(question, department=dept)
            results[dept] = dept_result

        return results

    async def hybrid_query(
        self,
        question: str,
        department: Optional[str] = None,
        db_results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Hibrit sorgu - hem RAG hem de veritabanı sonuçlarını birleştirir.

        Args:
            question: Kullanıcı sorusu
            department: Departman (opsiyonel)
            db_results: Veritabanından gelen sonuçlar

        Returns:
            Birleştirilmiş yanıt
        """
        # RAG sorgusu
        rag_result = await self.query(question, department, use_llm=False)

        # Bağlamları birleştir
        combined_context = ""

        if db_results:
            combined_context += "=== Veritabanı Bilgileri ===\n"
            combined_context += str(db_results) + "\n\n"

        if rag_result["sources"]:
            combined_context += "=== Doküman Bilgileri ===\n"
            combined_context += rag_result["answer"] + "\n"

        if not combined_context:
            return {
                "answer": "Bu konuda bilgi bulunamadı.",
                "sources": [],
                "db_results": None
            }

        # LLM ile yanıt üret
        try:
            prompt = f"""Aşağıdaki bilgilere dayanarak kullanıcının sorusunu yanıtla.

{combined_context}

Soru: {question}

Yanıtını Türkçe olarak, açık ve anlaşılır şekilde ver."""

            answer = await self.llm.generate(prompt)

            return {
                "answer": answer,
                "sources": rag_result["sources"],
                "db_results": db_results
            }

        except Exception as e:
            logger.error("hybrid_query_error", error=str(e))
            return {
                "answer": combined_context,
                "sources": rag_result["sources"],
                "db_results": db_results
            }
