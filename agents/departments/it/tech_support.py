"""
Tech Support Agent - Teknik destek agentı.

Bilgisayar, yazılım ve donanım sorunlarıyla ilgilenir.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.agent_card import AgentSkill
from agents.departments.base_department import BaseDepartmentAgent
from llm.provider import LLMProvider
from llm.prompts import SystemPrompts
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


class TechSupportAgent(BaseDepartmentAgent):
    """
    Teknik Destek Agentı.

    Sorumluluklar:
    - Bilgisayar sorunları
    - Yazılım hataları
    - Donanım arızaları
    - VPN ve bağlantı sorunları
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        db_connection: Optional[Any] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="it_tech_support",
            name="Teknik Destek Uzmanı",
            description="Bilgisayar, yazılım ve donanım sorunlarını çözer",
            department="it",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            db_connection=db_connection,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """Teknik destek yetenekleri."""
        return [
            AgentSkill(
                id="diagnose_hardware",
                name="Donanım Tanılama",
                description="Donanım sorunlarını teşhis eder",
                examples=["Bilgisayarım açılmıyor", "Yazıcı çalışmıyor"]
            ),
            AgentSkill(
                id="software_troubleshoot",
                name="Yazılım Sorun Giderme",
                description="Yazılım hatalarını giderir",
                examples=["Program çöküyor", "Uygulama açılmıyor"]
            ),
            AgentSkill(
                id="network_support",
                name="Ağ Desteği",
                description="Ağ ve bağlantı sorunlarını çözer",
                examples=["İnternete bağlanamıyorum", "VPN çalışmıyor"]
            )
        ]

    def _get_system_prompt(self) -> str:
        return SystemPrompts.IT_TECH_SUPPORT

    async def query_database(
        self,
        query: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """IT veritabanından bilgi çeker."""
        if not self.db:
            return None

        query_lower = query.lower()

        # Kullanıcı bilgisi varsa
        user_id = data.get("user_id") if data else None

        results = {}

        # Cihaz bilgisi sorgula
        if any(kw in query_lower for kw in ["bilgisayar", "laptop", "cihaz"]):
            if user_id:
                device_info = await self.db.get_user_devices(user_id)
                if device_info:
                    results["cihaz_bilgisi"] = device_info

        # Açık destek talepleri
        if user_id:
            tickets = await self.db.get_open_tickets(user_id, department="it")
            if tickets:
                results["acik_talepler"] = tickets

        # Bilinen sorunlar
        known_issues = await self.db.get_known_issues("tech_support")
        if known_issues:
            results["bilinen_sorunlar"] = known_issues[:3]  # İlk 3

        return results if results else None

    async def generate_agent_response(
        self,
        query: str,
        db_results: Optional[Dict[str, Any]] = None,
        rag_results: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Teknik destek yanıtı oluşturur."""
        # Standart sorun çözüm şablonları
        query_lower = query.lower()

        # Hızlı yanıtlar
        if "vpn" in query_lower and ("bağlan" in query_lower or "çalışmıyor" in query_lower):
            quick_response = """VPN bağlantı sorunu için şu adımları deneyin:
1. VPN uygulamasını kapatıp yeniden açın
2. İnternet bağlantınızı kontrol edin
3. VPN sunucu adresini kontrol edin: vpn.universite.edu.tr
4. Sorun devam ederse IT Destek Hattı: 1234"""

            if db_results:
                return f"{quick_response}\n\nEk Bilgi:\n{self._format_db_results(db_results)}"
            return quick_response

        # IT ile ilgili keyword kontrolu - sadece ilgili sorgularda veri dondur
        it_keywords = ["bilgisayar", "laptop", "yazilim", "yazılım", "vpn", "internet", "baglanti", "bağlantı", "teknik", "sorun", "hata", "cihaz"]
        has_relevant_keyword = any(kw in query_lower for kw in it_keywords)

        if not has_relevant_keyword:
            return "Bu konuda ilgili bilgi bulunamadi."

        # Ilgili sorgu - RAG varsa formatla
        if rag_results:
            answer = rag_results.get("answer", "")
            sources = rag_results.get("sources", [])
            if answer and answer.strip() and sources:
                return await super().generate_agent_response(query, db_results, rag_results, data)

        if db_results:
            return self._format_db_results(db_results)

        return "Bu konuda ilgili bilgi bulunamadi."
