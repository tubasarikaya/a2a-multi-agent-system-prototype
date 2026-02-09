"""
Finance Orchestrator - Mali İşler departmanı koordinatörü.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.protocol import A2ATask
from a2a.agent_card import AgentSkill
from agents.base_agent import DepartmentOrchestrator
from llm.provider import LLMProvider
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


# Mali işler alt-görev anahtar kelimeleri
FINANCE_TASK_KEYWORDS = {
    "tuition": [
        "harç", "ödeme", "borç", "taksit", "fatura", "ücret",
        "katkı payı", "öğrenim ücreti", "banka", "dekont",
        "makbuz", "iade", "indirim"
    ],
    "scholarship": [
        "burs", "kredi", "kyk", "yurt", "destek", "başvuru",
        "karşılıksız", "özel burs", "başarı bursu", "ihtiyaç",
        "sosyal yardım"
    ]
}


class FinanceOrchestrator(DepartmentOrchestrator):
    """
    Mali İşler Departmanı Orchestrator.

    Alt agentlar:
    - TuitionAgent: Harç ve ödeme işlemleri
    - ScholarshipAgent: Burs işlemleri
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="finance_orchestrator",
            name="Mali İşler Koordinatörü",
            description="Mali işler departmanı içi görev dağıtımını yönetir",
            department="finance",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """Mali işler orchestrator yetenekleri."""
        return [
            AgentSkill(
                id="route_finance_task",
                name="Mali İşler Görev Yönlendirme",
                description="Mali işler görevlerini uygun alt agent'a yönlendirir"
            ),
            AgentSkill(
                id="tuition",
                name="Harç İşlemleri",
                description="Harç ve ödeme işlemleri"
            ),
            AgentSkill(
                id="scholarship",
                name="Burs İşlemleri",
                description="Burs başvuru ve işlemleri"
            )
        ]

    async def route_task(self, task: A2ATask) -> str:
        """Task'ı hangi mali işler agent'ının işleyeceğini belirler."""
        query = task.initial_message.get_text().lower()

        # Anahtar kelime tabanlı routing
        tuition_score = sum(1 for kw in FINANCE_TASK_KEYWORDS["tuition"] if kw in query)
        scholarship_score = sum(1 for kw in FINANCE_TASK_KEYWORDS["scholarship"] if kw in query)

        if scholarship_score > tuition_score:
            return "finance_scholarship_agent"
        elif tuition_score > 0:
            return "finance_tuition_agent"

        # LLM ile karar ver
        if self.llm:
            try:
                prompt = f"""Mali işlere gelen istek: {query}

Bu istek hangi servis tarafından ele alınmalı?
1. tuition - Harç, ödeme, borç işlemleri
2. scholarship - Burs başvuru ve işlemleri

Sadece servis adını yaz (tuition veya scholarship):"""

                response = await self.llm.generate(prompt)
                response_lower = response.lower().strip()

                if "scholarship" in response_lower or "burs" in response_lower:
                    return "finance_scholarship_agent"
                elif "tuition" in response_lower or "harç" in response_lower:
                    return "finance_tuition_agent"
            except Exception as e:
                logger.warning("finance_routing_llm_fallback", error=str(e))

        # Default: tuition
        return "finance_tuition_agent"
