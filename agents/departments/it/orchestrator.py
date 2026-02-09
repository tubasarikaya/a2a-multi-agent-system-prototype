"""
IT Department Orchestrator - IT departmanı koordinatörü.
"""
from typing import Any, Dict, List, Optional
import structlog

from a2a.protocol import A2ATask
from a2a.agent_card import AgentSkill
from agents.base_agent import DepartmentOrchestrator
from llm.provider import LLMProvider
from llm.prompts import SystemPrompts
from rag.rag_engine import RAGEngine

logger = structlog.get_logger()


# IT alt-görev anahtar kelimeleri
IT_TASK_KEYWORDS = {
    "tech_support": [
        "bilgisayar", "laptop", "yazıcı", "printer", "yazılım",
        "program", "uygulama", "hata", "çalışmıyor", "donuyor",
        "yavaş", "vpn", "bağlantı", "driver", "sürücü", "ekran",
        "klavye", "mouse", "fare"
    ],
    "email_support": [
        "şifre", "parola", "password", "e-posta", "email", "mail",
        "hesap", "kullanıcı", "giriş", "login", "erişim", "unuttum",
        "sıfırlama", "değiştirme", "kilitleme", "spam", "virüs"
    ]
}


class ITOrchestrator(DepartmentOrchestrator):
    """
    IT Departmanı Orchestrator.

    Alt agentlar:
    - TechSupportAgent: Teknik destek (donanım, yazılım)
    - EmailSupportAgent: E-posta ve hesap işlemleri
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        endpoint: str = "http://localhost:8000"
    ):
        super().__init__(
            agent_id="it_orchestrator",
            name="IT Departmanı Koordinatörü",
            description="IT departmanı içi görev dağıtımını yönetir",
            department="it",
            llm_provider=llm_provider,
            rag_engine=rag_engine,
            endpoint=endpoint
        )

    def _get_skills(self) -> List[AgentSkill]:
        """IT orchestrator yetenekleri."""
        return [
            AgentSkill(
                id="route_it_task",
                name="IT Görev Yönlendirme",
                description="IT görevlerini uygun alt agent'a yönlendirir"
            ),
            AgentSkill(
                id="tech_support",
                name="Teknik Destek",
                description="Donanım ve yazılım sorunları"
            ),
            AgentSkill(
                id="email_support",
                name="E-posta Destek",
                description="E-posta ve hesap işlemleri"
            )
        ]

    async def route_task(self, task: A2ATask) -> str:
        """Task'ı hangi IT agent'ının işleyeceğini belirler."""
        query = task.initial_message.get_text().lower()

        # Anahtar kelime tabanlı routing
        tech_score = sum(1 for kw in IT_TASK_KEYWORDS["tech_support"] if kw in query)
        email_score = sum(1 for kw in IT_TASK_KEYWORDS["email_support"] if kw in query)

        if email_score > tech_score:
            return "it_email_support"
        elif tech_score > 0:
            return "it_tech_support"

        # LLM ile karar ver
        if self.llm:
            try:
                prompt = f"""IT departmanına gelen istek: {query}

Bu istek hangi IT servisi tarafından ele alınmalı?
1. tech_support - Donanım, yazılım, bilgisayar sorunları
2. email_support - E-posta, hesap, şifre işlemleri

Sadece servis adını yaz (tech_support veya email_support):"""

                response = await self.llm.generate(prompt)
                response_lower = response.lower().strip()

                if "email" in response_lower:
                    return "it_email_support"
                elif "tech" in response_lower:
                    return "it_tech_support"
            except Exception as e:
                logger.warning("it_routing_llm_fallback", error=str(e))

        # Default: tech support
        return "it_tech_support"
