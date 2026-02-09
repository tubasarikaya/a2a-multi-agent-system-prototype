"""
Base Department Agent - Departman agentları için temel sınıf.

Her departman agentı veritabanı ve RAG erişimine sahiptir.
"""
from abc import abstractmethod
from typing import Any, Dict, Optional
import asyncio
import structlog

from a2a.protocol import A2ATask, create_response, create_error_response
from a2a.agent_card import AgentSkill
from agents.base_agent import BaseAgent
from llm.provider import LLMProvider
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


class BaseDepartmentAgent(BaseAgent):
    """
    Departman seviyesi agent temel sınıfı.
    Veritabanı ve RAG entegrasyonu ile birlikte gelir.
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        department: str,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        db_connection: Optional[Any] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id=agent_id,
            name=name,
            description=description,
            department=department,
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            endpoint=endpoint
        )

        self.db = db_connection

    async def process_task(self, task: A2ATask) -> A2ATask:
        """
        Task işleme akışı:
        1. Veritabanından ilgili verileri çek
        2. RAG ile doküman ara
        3. LLM ile yanıt oluştur
        """
        query = task.initial_message.get_text()
        data = task.initial_message.get_data()

        try:
            # Veritabanı sorgusu
            db_results = await self.query_database(query, data)

            # RAG sorgusu
            rag_results = None
            if self.rag:
                rag_results = await self.rag.query(
                    question=query,
                    department=self.department,
                    use_llm=False  # LLM çağrısını devre dışı bırak, yalnızca doküman getir
                )

            # Yanıt oluştur
            response = await self.generate_agent_response(
                query=query,
                db_results=db_results,
                rag_results=rag_results,
                data=data
            )

            return create_response(task, response)

        except Exception as e:
            logger.error(
                "department_agent_error",
                agent_id=self.agent_id,
                error=str(e)
            )
            return create_error_response(task, str(e))

    @abstractmethod
    async def query_database(
        self,
        query: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Veritabanı sorgusu yapar.
        Alt sınıflar implement eder.
        """
        pass

    async def generate_agent_response(
        self,
        query: str,
        db_results: Optional[Dict[str, Any]] = None,
        rag_results: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Veritabanı ve RAG sonuçlarını kullanarak yanıt üretir.
        RAG sonuçlarını LLM ile formatlar (kontrollü - sadece formatlama, yeni bilgi eklemez).
        """
        # Kullanıcı ID kontrolü - kişiye özel sorgular için
        user_id = data.get("user_id") if data else None
        query_lower = query.lower()
        
        # Kişiye özel sorgu tespiti
        personal_keywords = ["borcum", "borçum", "durumum", "notum", "notlarım", "kaydım", "kayıt durumum", 
                            "gpa'm", "gano'm", "kredim", "kredilerim", "ödemem", "odeme"]
        is_personal_query = any(kw in query_lower for kw in personal_keywords)
        
        # RAG sonuçları var mı ve içerik var mı kontrol et
        has_rag_content = False
        if rag_results:
            answer = rag_results.get("answer", "")
            sources = rag_results.get("sources", [])
            # Gerçek içerik var mı?
            has_rag_content = bool(answer and answer.strip() and sources)

        # RAG'den gerçek içerik geldiyse formatla
        if has_rag_content:
            formatted_rag = await self._format_rag_results(query, rag_results, db_results)
            if formatted_rag and "bilgi bulunamadı" not in formatted_rag.lower():
                return formatted_rag

        # DB verisi varsa biçimle ve dön
        if db_results:
            return self._format_db_results(db_results)

        # Kişiye özel sorgu ama öğrenci ID yok
        if is_personal_query and not user_id:
            return "Bu sorgu için öğrenci numaranız gereklidir. Lütfen öğrenci numaranızı belirtin (/user <numara>)."
        
        # Kişiye özel sorgu ama öğrenci bulunamadı
        if is_personal_query and user_id:
            return f"Öğrenci numarası '{user_id}' ile ilgili kayıt bulunamadı. Lütfen öğrenci numaranızı kontrol edin."
        
        # Genel bilgi sorgusu - RAG'den bilgi gelmemiş
        return "Bu konuda ilgili bilgi bulunamadı. Lütfen sorunuzu farklı şekilde ifade edin veya ilgili birime doğrudan başvurun."
    
    async def _format_rag_results(
        self,
        query: str,
        rag_results: Dict[str, Any],
        db_results: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        RAG sonuçlarını LLM ile formatlar.
        Sadece formatlama yapar, yeni bilgi eklemez.
        """
        answer = rag_results.get("answer", "")
        sources = rag_results.get("sources", [])

        # Boş cevap kontrolü
        if not answer or not answer.strip():
            return None

        # Eğer answer zaten formatlanmışsa (LLM'den gelmişse) direkt döndür
        if answer and not answer.startswith("[Kaynak"):
            cleaned = self._clean_rag_answer(answer)
            if db_results:
                db_info = self._format_db_results(db_results)
                return f"{cleaned}\n\n{db_info}" if db_info else cleaned
            return cleaned

        # LLM yoksa ham cevabı temizleyip döndür
        if not self.llm:
            cleaned = self._clean_rag_answer(answer)
            return cleaned

        # Ham RAG sonuçlarını formatla (LLM ile)
        try:
            prompt = f"""Kullanıcı sorusu: "{query}"

Aşağıdaki bilgileri kullanarak kullanıcıya net ve anlaşılır bir cevap oluştur.

KURALLAR:
- Emoji KULLANMA
- SADECE verilen bilgileri kullan, yeni bilgi ekleme
- Bilgilerde cevap YOKSA, "Bu konuda ilgili bilgi bulunamadı." yaz
- Kaynak referanslarını ([Kaynak X] gibi) kaldır
- Kısa ve öz yanıt ver
- Gereksiz süsleme yapma

Bilgiler:
{answer}

Yanıt:"""

            # Karmaşık sorularda daha fazla token ve timeout
            word_count = len(query.split())
            is_complex = word_count > 15 or len(query) > 100 or query.count("?") > 1
            
            max_tokens = 1500 if is_complex else 1200
            timeout_seconds = 25.0 if is_complex else 20.0
            
            formatted = await asyncio.wait_for(
                self.llm.generate(prompt, system_prompt=self._get_system_prompt(), max_tokens=max_tokens),
                timeout=timeout_seconds
            )

            if formatted:
                formatted = self._remove_emojis(formatted)

            if db_results:
                db_info = self._format_db_results(db_results)
                return f"{formatted}\n\n{db_info}" if db_info else formatted

            return formatted

        except Exception as e:
            logger.warning("rag_formatting_failed",
                         error=str(e),
                         department=self.department,
                         query_preview=query[:100])
            cleaned = self._clean_rag_answer(answer)
            return cleaned

    def _remove_emojis(self, text: str) -> str:
        """Metinden emojileri kaldırır."""
        import re
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF"
            "\U0001FA00-\U0001FA6F"
            "\U0001FA70-\U0001FAFF"
            "\U00002600-\U000026FF"
            "]+",
            flags=re.UNICODE
        )
        return emoji_pattern.sub('', text).strip()
    
    def _clean_rag_answer(self, answer: str) -> str:
        """
        RAG cevabından kaynak referanslarını temizler (basit regex ile).
        LLM kullanmadan hızlı temizleme.
        """
        import re
        # [Kaynak X - ...] formatını kaldır
        cleaned = re.sub(r'\[Kaynak \d+[^\]]*\]\n?', '', answer)
        # Çoklu boş satırları tek boş satıra çevir
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def _format_db_results(self, results: Dict[str, Any]) -> str:
        """Veritabanı sonuçlarını formatlar."""
        if not results:
            return "Veri bulunamadı."

        lines = []
        for key, value in results.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  - {k}: {v}")
            elif isinstance(value, list):
                lines.append(f"{key}: {', '.join(str(v) for v in value)}")
            else:
                lines.append(f"{key}: {value}")

        return "\n".join(lines)

    @abstractmethod
    def _get_system_prompt(self) -> str:
        """Agent'a özgü sistem promptu. Alt sınıflar implement eder."""
        pass
