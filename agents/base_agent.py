"""
Base Agent - Tüm agent'lar için temel sınıf.
"""
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional
import structlog

from a2a.protocol import (
    A2ATask,
    TaskStatus,
    create_response,
    create_error_response,
    Artifact,
    TextPart
)
from a2a.agent_card import AgentCard, AgentSkill, AgentCapability, agent_registry
from a2a.client import A2AClient
from llm.provider import LLMProvider
from rag.rag_engine import RAGEngine
import asyncio

logger = structlog.get_logger()


class BaseAgent(ABC):
    """
    Temel Agent sınıfı.
    Tüm agent'lar bu sınıftan türetilir.
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        department: Optional[str] = None,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
        endpoint: str = "http://localhost:8000"
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.department = department
        self.llm = llm_provider
        self.rag = rag_engine
        self.endpoint = endpoint

        # A2A client
        self._client: Optional[A2AClient] = None

        # Agent card
        self._agent_card = self._create_agent_card()

        # Registry'ye kaydet
        agent_registry.register(self._agent_card)

        # Basit circuit breaker / retry ayarları
        self._default_timeout = 10  # saniye
        self._max_retries = 2
        self._retry_backoff = 0.5  # saniye
        self._cb_fail_threshold = 3
        self._cb_reset_after = 15  # saniye
        self._cb_fail_count = 0
        self._cb_open_until: Optional[float] = None

        # Bağlamsal logger
        self._log = logger.bind(agent_id=self.agent_id, department=self.department)

        self._log.info(
            "agent_created",
            agent_id=agent_id,
            department=department
        )

    def _create_agent_card(self) -> AgentCard:
        """Agent kartı oluşturur."""
        return AgentCard(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            endpoint=self.endpoint,
            department=self.department,
            skills=self._get_skills(),
            capabilities=AgentCapability(
                streaming=False,
                push_notifications=False,
                multi_turn=True,
                async_execution=True
            ),
            metadata={"is_orchestrator": False}
        )

    @abstractmethod
    def _get_skills(self) -> list[AgentSkill]:
        """Agent'ın yeteneklerini döndürür. Alt sınıflar implement eder."""
        pass

    @abstractmethod
    async def process_task(self, task: A2ATask) -> A2ATask:
        """
        Task'ı işler. Alt sınıflar implement eder.

        Args:
            task: İşlenecek A2A task

        Returns:
            İşlenmiş task (status güncellenmiş)
        """
        pass

    async def handle_task(self, task: A2ATask) -> A2ATask:
        """
        Task handler wrapper - hata yönetimi ve logging ekler.
        Bu method doğrudan çağrılır veya A2A server'a verilir.
        """
        try:
            logger.info(
                "task_received",
                agent_id=self.agent_id,
                task_id=task.task_id,
                from_agent=task.from_agent
            )

            task.update_status(TaskStatus.WORKING)

            # Alt sınıfın process metodunu çağır
            result = await self.process_task(task)

            logger.info(
                "task_completed",
                agent_id=self.agent_id,
                task_id=task.task_id,
                status=result.status
            )

            return result

        except Exception as e:
            logger.error(
                "task_error",
                agent_id=self.agent_id,
                task_id=task.task_id,
                error=str(e)
            )
            return create_error_response(task, str(e))

    def get_client(self) -> A2AClient:
        """A2A client döndürür."""
        if self._client is None:
            self._client = A2AClient(self.agent_id)
        return self._client

    def register_peer(self, peer_agent_id: str, handler: Callable):
        """
        Lokal peer agent kaydeder (aynı process'te).
        HTTP yerine doğrudan çağrı yapılır.
        """
        client = self.get_client()
        client.register_local_handler(peer_agent_id, handler)

    async def send_to_agent(
        self,
        to_agent: str,
        text: str,
        data: Optional[Dict[str, Any]] = None,
        context_id: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_backoff: Optional[float] = None
    ) -> A2ATask:
        """Başka bir agent'a task gönderir."""
        client = self.get_client()
        t_timeout = timeout if timeout is not None else self._default_timeout
        t_retries = max_retries if max_retries is not None else self._max_retries
        t_backoff = retry_backoff if retry_backoff is not None else self._retry_backoff

        # Circuit breaker: açık mı?
        now = time.monotonic()
        if self._cb_open_until and now < self._cb_open_until:
            raise RuntimeError("Circuit breaker open - skipping send_to_agent")

        last_exc = None
        for attempt in range(t_retries + 1):
            start = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    client.send_task(
                        to_agent=to_agent,
                        text=text,
                        data=data,
                        context_id=context_id
                    ),
                    timeout=t_timeout
                )
                # Başarılı -> circuit breaker reset + latency log
                latency_ms = (time.monotonic() - start) * 1000
                self._log.info(
                    "send_to_agent_success",
                    to_agent=to_agent,
                    attempt=attempt + 1,
                    latency_ms=round(latency_ms, 2),
                    context_id=context_id
                )
                self._reset_circuit_breaker()
                return result
            except asyncio.TimeoutError as e:
                last_exc = e
                self._log.warning(
                    "send_to_agent_timeout",
                    to_agent=to_agent,
                    attempt=attempt + 1,
                    timeout=t_timeout,
                    latency_ms=round((time.monotonic() - start) * 1000, 2),
                    context_id=context_id
                )
            except Exception as e:
                last_exc = e
                self._log.warning(
                    "send_to_agent_retry",
                    to_agent=to_agent,
                    attempt=attempt + 1,
                    error=str(e),
                    latency_ms=round((time.monotonic() - start) * 1000, 2),
                    context_id=context_id
                )

            if attempt < t_retries:
                await asyncio.sleep(t_backoff)

        # Başarısız -> circuit breaker aç
        self._cb_fail_count += 1
        if self._cb_fail_count >= self._cb_fail_threshold:
            self._cb_open_until = time.monotonic() + self._cb_reset_after
            self._log.error(
                "circuit_breaker_opened",
                to_agent=to_agent,
                fails=self._cb_fail_count,
                open_seconds=self._cb_reset_after,
                context_id=context_id
            )

        raise RuntimeError(f"send_to_agent failed after retries: {last_exc}")

    def _reset_circuit_breaker(self):
        """Başarılı çağrı sonrası circuit breaker sayaçlarını sıfırla."""
        self._cb_fail_count = 0
        self._cb_open_until = None

    async def query_rag(
        self,
        question: str,
        department: Optional[str] = None
    ) -> Dict[str, Any]:
        """RAG sorgusu yapar."""
        if self.rag is None:
            return {"answer": "RAG engine yapılandırılmamış.", "sources": []}

        return await self.rag.query(
            question=question,
            department=department or self.department
        )

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """LLM ile yanıt üretir."""
        if self.llm is None:
            return "LLM provider yapılandırılmamış."

        return await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt
        )

    def create_artifact(
        self,
        name: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Artifact:
        """Artifact oluşturur."""
        return Artifact(
            name=name,
            parts=[TextPart(text=content)],
            metadata=metadata or {}
        )

    @property
    def agent_card(self) -> AgentCard:
        """Agent kartını döndürür."""
        return self._agent_card


class DepartmentOrchestrator(BaseAgent):
    """
    Departman Orchestrator - Departman içi iş dağıtımını yönetir.
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        department: str,
        llm_provider: Optional[LLMProvider] = None,
        rag_engine: Optional[RAGEngine] = None,
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

        # Alt agent'lar
        self._sub_agents: Dict[str, BaseAgent] = {}

    def _create_agent_card(self) -> AgentCard:
        """Orchestrator için agent kartı."""
        card = super()._create_agent_card()
        card.metadata["is_orchestrator"] = True
        return card

    def register_sub_agent(self, agent: BaseAgent):
        """Alt agent kaydeder."""
        self._sub_agents[agent.agent_id] = agent
        # Lokal handler olarak kaydet
        self.register_peer(agent.agent_id, agent.handle_task)
        logger.info(
            "sub_agent_registered",
            orchestrator=self.agent_id,
            sub_agent=agent.agent_id
        )

    def get_sub_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """Alt agent döndürür."""
        return self._sub_agents.get(agent_id)

    def get_sub_agents(self) -> list[BaseAgent]:
        """Tüm alt agent'ları döndürür."""
        return list(self._sub_agents.values())

    def _get_skills(self) -> list[AgentSkill]:
        """Orchestrator yetenekleri."""
        return [
            AgentSkill(
                id="route_task",
                name="Görev Yönlendirme",
                description="Gelen görevleri uygun alt agent'lara yönlendirir"
            ),
            AgentSkill(
                id="aggregate_results",
                name="Sonuç Birleştirme",
                description="Alt agent sonuçlarını birleştirir"
            )
        ]

    @abstractmethod
    async def route_task(self, task: A2ATask) -> str:
        """
        Task'ı hangi alt agent'ın işleyeceğini belirler.
        Returns: agent_id
        """
        pass

    async def process_task(self, task: A2ATask) -> A2ATask:
        """Task'ı uygun alt agent'a yönlendirir."""
        # Hangi agent işleyecek?
        target_agent_id = await self.route_task(task)

        if target_agent_id not in self._sub_agents:
            return create_error_response(
                task,
                f"Alt agent bulunamadı: {target_agent_id}"
            )

        # Alt agent'a gönder
        result = await self.send_to_agent(
            to_agent=target_agent_id,
            text=task.initial_message.get_text(),
            data=task.initial_message.get_data(),
            context_id=task.context_id
        )

        # Ana task'ı güncelle
        if result.status == TaskStatus.COMPLETED:
            response_text = result.get_latest_message().get_text()
            return create_response(task, response_text)
        else:
            return create_error_response(task, result.error or "Alt agent hatası")
