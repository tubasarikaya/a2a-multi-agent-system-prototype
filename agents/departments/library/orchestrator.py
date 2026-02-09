"""
Library Orchestrator - Kütüphane departmanı koordinatörü.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.protocol import A2ATask
from a2a.agent_card import AgentSkill
from agents.base_agent import DepartmentOrchestrator
from llm.provider import LLMProvider
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


# Kütüphane alt-görev anahtar kelimeleri
LIBRARY_TASK_KEYWORDS = {
    "book": [
        "kitap", "ödünç", "iade", "uzatma", "rezervasyon",
        "kitap ara", "kitap bul", "yayın", "dergi"
    ],
    "card": [
        "kütüphane kartı", "kart", "üyelik", "kayıt"
    ]
}


class LibraryOrchestrator(DepartmentOrchestrator):
    """
    Kütüphane Departmanı Orchestrator.

    Alt agentlar:
    - BookAgent: Kitap arama ve ödünç işlemleri
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="library_orchestrator",
            name="Kütüphane Koordinatörü",
            description="Kütüphane departmanı içi görev dağıtımını yönetir",
            department="library",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """Kütüphane orchestrator yetenekleri."""
        return [
            AgentSkill(
                id="route_library_task",
                name="Kütüphane Görev Yönlendirme",
                description="Kütüphane görevlerini uygun alt agent'a yönlendirir"
            ),
            AgentSkill(
                id="book_operations",
                name="Kitap İşlemleri",
                description="Kitap arama, ödünç alma, iade işlemleri"
            )
        ]

    async def route_task(self, task: A2ATask) -> str:
        """Task'ı hangi kütüphane agent'ının işleyeceğini belirler."""
        query = task.initial_message.get_text().lower()
        data = task.initial_message.get_data() or {}
        task_type = data.get("task_type", "")

        # Task type ile direkt routing
        if task_type in ["search_book", "check_library_card"]:
            return "library_book_agent"

        # Anahtar kelime tabanlı routing
        book_score = sum(1 for kw in LIBRARY_TASK_KEYWORDS["book"] if kw in query)
        card_score = sum(1 for kw in LIBRARY_TASK_KEYWORDS["card"] if kw in query)

        # Şimdilik tek agent var
        return "library_book_agent"
