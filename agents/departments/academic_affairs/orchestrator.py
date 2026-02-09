"""
Academic Affairs Orchestrator - Akademik İşler departmanı koordinatörü.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.protocol import A2ATask
from a2a.agent_card import AgentSkill
from agents.base_agent import DepartmentOrchestrator
from llm.provider import LLMProvider
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


# Akademik işler alt-görev anahtar kelimeleri
ACADEMIC_TASK_KEYWORDS = {
    "status": [
        "akademik durum", "gpa", "not ortalaması", "kredi",
        "dönem", "akademik", "mezuniyet şartı", "ders sayısı"
    ],
    "transcript": [
        "transkript", "not dökümü", "belgeler", "not belgesi"
    ]
}


class AcademicAffairsOrchestrator(DepartmentOrchestrator):
    """
    Akademik İşler Departmanı Orchestrator.

    Alt agentlar:
    - AcademicStatusAgent: Akademik durum sorgulama
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="academic_affairs_orchestrator",
            name="Akademik İşler Koordinatörü",
            description="Akademik işler departmanı içi görev dağıtımını yönetir",
            department="academic_affairs",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """Akademik işler orchestrator yetenekleri."""
        return [
            AgentSkill(
                id="route_academic_task",
                name="Akademik İşler Görev Yönlendirme",
                description="Akademik işler görevlerini uygun alt agent'a yönlendirir"
            ),
            AgentSkill(
                id="academic_status",
                name="Akademik Durum Sorgulama",
                description="GPA, kredi durumu ve akademik durum sorgulama"
            )
        ]

    async def route_task(self, task: A2ATask) -> str:
        """Task'ı hangi akademik işler agent'ının işleyeceğini belirler."""
        query = task.initial_message.get_text().lower()
        data = task.initial_message.get_data() or {}
        task_type = data.get("task_type", "")

        # Task type ile direkt routing
        if task_type == "check_academic_status":
            return "academic_status_agent"

        # Anahtar kelime tabanlı routing
        status_score = sum(1 for kw in ACADEMIC_TASK_KEYWORDS["status"] if kw in query)
        transcript_score = sum(1 for kw in ACADEMIC_TASK_KEYWORDS["transcript"] if kw in query)

        if transcript_score > status_score:
            return "academic_status_agent"  # Şimdilik aynı agent
        elif status_score > 0:
            return "academic_status_agent"

        # Default
        return "academic_status_agent"
