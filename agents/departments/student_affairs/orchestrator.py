"""
Student Affairs Orchestrator - Öğrenci İşleri departmanı koordinatörü.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.protocol import A2ATask
from a2a.agent_card import AgentSkill
from agents.base_agent import DepartmentOrchestrator
from llm.provider import LLMProvider
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


# Öğrenci işleri alt-görev anahtar kelimeleri
STUDENT_TASK_KEYWORDS = {
    "registration": [
        "kayıt", "belge", "transkript", "diploma", "ilişik kesme",
        "öğrenci belgesi", "askerlik", "durum belgesi", "onay",
        "kayıt dondurma", "kayıt silme", "yatay geçiş", "dikey geçiş",
        "mezuniyet", "tez", "staj"
    ],
    "course": [
        "ders", "seçim", "kayıt", "program", "müfredat", "kredi",
        "dönem", "final", "vize", "sınav", "not", "harf notu",
        "devamsızlık", "ek sınav", "bütünleme", "ön koşul",
        "danışman", "ders saydırma", "muafiyet"
    ]
}


class StudentAffairsOrchestrator(DepartmentOrchestrator):
    """
    Öğrenci İşleri Departmanı Orchestrator.

    Alt agentlar:
    - RegistrationAgent: Kayıt ve belge işlemleri
    - CourseAgent: Ders işlemleri
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="student_affairs_orchestrator",
            name="Öğrenci İşleri Koordinatörü",
            description="Öğrenci işleri departmanı içi görev dağıtımını yönetir",
            department="student_affairs",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """Öğrenci işleri orchestrator yetenekleri."""
        return [
            AgentSkill(
                id="route_student_task",
                name="Öğrenci İşleri Görev Yönlendirme",
                description="Öğrenci işleri görevlerini uygun alt agent'a yönlendirir"
            ),
            AgentSkill(
                id="registration",
                name="Kayıt İşlemleri",
                description="Kayıt ve belge işlemleri"
            ),
            AgentSkill(
                id="course",
                name="Ders İşlemleri",
                description="Ders kaydı ve akademik işlemler"
            )
        ]

    async def route_task(self, task: A2ATask) -> str:
        """Task'ı hangi öğrenci işleri agent'ının işleyeceğini belirler."""
        query = task.initial_message.get_text().lower()

        # Anahtar kelime tabanlı routing
        reg_score = sum(1 for kw in STUDENT_TASK_KEYWORDS["registration"] if kw in query)
        course_score = sum(1 for kw in STUDENT_TASK_KEYWORDS["course"] if kw in query)

        # "ders kaydı" özel durumu - course agent
        if "ders" in query and "kayıt" in query:
            return "student_course_agent"

        if course_score > reg_score:
            return "student_course_agent"
        elif reg_score > 0:
            return "student_registration_agent"

        # LLM ile karar ver
        if self.llm:
            try:
                prompt = f"""Öğrenci işlerine gelen istek: {query}

Bu istek hangi servis tarafından ele alınmalı?
1. registration - Kayıt, belge, transkript, mezuniyet işlemleri
2. course - Ders seçimi, notlar, akademik işlemler

Sadece servis adını yaz (registration veya course):"""

                response = await self.llm.generate(prompt)
                response_lower = response.lower().strip()

                if "course" in response_lower or "ders" in response_lower:
                    return "student_course_agent"
                elif "registration" in response_lower or "kayıt" in response_lower:
                    return "student_registration_agent"
            except Exception as e:
                logger.warning("student_routing_llm_fallback", error=str(e))

        # Default: registration
        return "student_registration_agent"
