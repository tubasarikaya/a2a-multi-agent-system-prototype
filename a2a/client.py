"""
A2A Client - Agent'ların diğer agent'larla iletişim kurmasını sağlar.
"""
import asyncio
from typing import Any, Callable, Dict, Optional
import httpx
import structlog

from .protocol import (
    A2ATask,
    A2AMessage,
    TaskStatus,
    create_task,
    create_error_response,
)
from .agent_card import AgentCard, agent_registry

logger = structlog.get_logger()


class A2AClient:
    """
    A2A İstemci - Diğer agent'lara task gönderir ve yanıt alır.
    """

    def __init__(
        self,
        agent_id: str,
        timeout: float = 30.0,
        local_handlers: Optional[Dict[str, Callable]] = None
    ):
        self.agent_id = agent_id
        self.timeout = timeout
        self._local_handlers: Dict[str, Callable] = local_handlers or {}
        self._http_client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._http_client:
            await self._http_client.aclose()

    def register_local_handler(self, agent_id: str, handler: Callable):
        """
        Lokal handler kaydet - aynı process'te çalışan agent'lar için.
        HTTP yerine doğrudan çağrı yapılır.
        """
        self._local_handlers[agent_id] = handler
        logger.info("local_handler_registered", agent_id=agent_id)

    async def send_task(
        self,
        to_agent: str,
        text: str,
        data: Optional[Dict[str, Any]] = None,
        context_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> A2ATask:
        """
        Başka bir agent'a task gönderir.
        Önce lokal handler kontrol edilir, yoksa HTTP isteği yapılır.
        """
        task = create_task(
            from_agent=self.agent_id,
            to_agent=to_agent,
            text=text,
            data=data,
            context_id=context_id,
            parent_task_id=parent_task_id,
            metadata=metadata
        )

        logger.info(
            "sending_task",
            task_id=task.task_id,
            from_agent=self.agent_id,
            to_agent=to_agent
        )

        # Lokal handler varsa kullan
        if to_agent in self._local_handlers:
            return await self._send_local(task)

        # HTTP ile gönder
        return await self._send_http(task)

    async def _send_local(self, task: A2ATask) -> A2ATask:
        """Lokal handler'a task gönderir (aynı process)."""
        handler = self._local_handlers.get(task.to_agent)
        if not handler:
            return create_error_response(task, f"Handler bulunamadı: {task.to_agent}")

        try:
            logger.debug("sending_local", task_id=task.task_id, to_agent=task.to_agent)
            task.update_status(TaskStatus.WORKING)

            # Handler'ı çağır
            if asyncio.iscoroutinefunction(handler):
                result = await handler(task)
            else:
                result = handler(task)

            return result

        except Exception as e:
            logger.error("local_handler_error", task_id=task.task_id, error=str(e))
            return create_error_response(task, str(e))

    async def _send_http(self, task: A2ATask) -> A2ATask:
        """HTTP ile remote agent'a task gönderir."""
        # Agent kartını bul
        agent_card = agent_registry.get(task.to_agent)
        if not agent_card:
            return create_error_response(
                task,
                f"Agent bulunamadı: {task.to_agent}"
            )

        endpoint = f"{agent_card.endpoint}/tasks"

        try:
            if not self._http_client:
                self._http_client = httpx.AsyncClient(timeout=self.timeout)

            logger.debug(
                "sending_http",
                task_id=task.task_id,
                endpoint=endpoint
            )

            response = await self._http_client.post(
                endpoint,
                json=task.model_dump(),
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                result_data = response.json()
                return A2ATask(**result_data)
            else:
                return create_error_response(
                    task,
                    f"HTTP hatası: {response.status_code} - {response.text}"
                )

        except httpx.TimeoutException:
            logger.error("http_timeout", task_id=task.task_id, endpoint=endpoint)
            return create_error_response(task, "Zaman aşımı")

        except Exception as e:
            logger.error("http_error", task_id=task.task_id, error=str(e))
            return create_error_response(task, str(e))

    async def send_tasks_parallel(
        self,
        tasks: list[tuple[str, str, Optional[Dict[str, Any]]]]
    ) -> list[A2ATask]:
        """
        Birden fazla task'ı paralel olarak gönderir.
        tasks: [(to_agent, text, data), ...]
        """
        async def send_one(to_agent: str, text: str, data: Optional[Dict[str, Any]]):
            return await self.send_task(to_agent, text, data)

        coroutines = [send_one(to, text, data) for to, text, data in tasks]
        return await asyncio.gather(*coroutines)

    async def get_task_status(self, agent_id: str, task_id: str) -> Optional[A2ATask]:
        """Bir task'ın durumunu sorgular."""
        agent_card = agent_registry.get(agent_id)
        if not agent_card:
            return None

        endpoint = f"{agent_card.endpoint}/tasks/{task_id}"

        try:
            if not self._http_client:
                self._http_client = httpx.AsyncClient(timeout=self.timeout)

            response = await self._http_client.get(endpoint)

            if response.status_code == 200:
                return A2ATask(**response.json())
            return None

        except Exception as e:
            logger.error("get_task_status_error", task_id=task_id, error=str(e))
            return None

    async def cancel_task(self, agent_id: str, task_id: str) -> bool:
        """Bir task'ı iptal eder."""
        agent_card = agent_registry.get(agent_id)
        if not agent_card:
            return False

        endpoint = f"{agent_card.endpoint}/tasks/{task_id}/cancel"

        try:
            if not self._http_client:
                self._http_client = httpx.AsyncClient(timeout=self.timeout)

            response = await self._http_client.post(endpoint)
            return response.status_code == 200

        except Exception as e:
            logger.error("cancel_task_error", task_id=task_id, error=str(e))
            return False
