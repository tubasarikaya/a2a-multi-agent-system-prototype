"""
A2A Server - Agent'ların HTTP üzerinden task almasını sağlar.
"""
from typing import Any, Callable, Dict, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import structlog

from .protocol import A2ATask, TaskStatus, create_error_response
from .agent_card import AgentCard

logger = structlog.get_logger()


class A2AServer:
    """
    A2A Sunucu - HTTP endpoint'leri üzerinden task alır ve işler.
    """

    def __init__(
        self,
        agent_card: AgentCard,
        task_handler: Callable[[A2ATask], A2ATask]
    ):
        self.agent_card = agent_card
        self.task_handler = task_handler
        self._tasks: Dict[str, A2ATask] = {}
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        """FastAPI uygulaması oluşturur."""
        app = FastAPI(
            title=f"{self.agent_card.name} A2A Server",
            description=self.agent_card.description,
            version=self.agent_card.version
        )

        @app.get("/.well-known/agent.json")
        async def get_agent_card():
            """Agent kartını döndürür (A2A discovery)."""
            return self.agent_card.to_well_known()

        @app.post("/tasks")
        async def create_task(request: Request):
            """Yeni task alır ve işler."""
            try:
                data = await request.json()
                task = A2ATask(**data)

                logger.info(
                    "task_received",
                    task_id=task.task_id,
                    from_agent=task.from_agent
                )

                # Task'ı kaydet
                self._tasks[task.task_id] = task

                # Handler'ı çağır
                result = await self._process_task(task)

                # Sonucu güncelle
                self._tasks[task.task_id] = result

                return JSONResponse(content=result.model_dump())

            except Exception as e:
                logger.error("task_processing_error", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/tasks/{task_id}")
        async def get_task(task_id: str):
            """Task durumunu döndürür."""
            task = self._tasks.get(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task bulunamadı")
            return task.model_dump()

        @app.post("/tasks/{task_id}/cancel")
        async def cancel_task(task_id: str):
            """Task'ı iptal eder."""
            task = self._tasks.get(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task bulunamadı")

            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                raise HTTPException(
                    status_code=400,
                    detail="Tamamlanmış veya başarısız task iptal edilemez"
                )

            task.update_status(TaskStatus.CANCELED)
            self._tasks[task_id] = task

            return {"status": "canceled"}

        @app.get("/health")
        async def health_check():
            """Sağlık kontrolü."""
            return {
                "status": "healthy",
                "agent_id": self.agent_card.agent_id,
                "agent_name": self.agent_card.name
            }

        return app

    async def _process_task(self, task: A2ATask) -> A2ATask:
        """Task'ı işler."""
        try:
            task.update_status(TaskStatus.WORKING)

            # Async handler kontrolü
            import asyncio
            if asyncio.iscoroutinefunction(self.task_handler):
                result = await self.task_handler(task)
            else:
                result = self.task_handler(task)

            return result

        except Exception as e:
            logger.error(
                "task_handler_error",
                task_id=task.task_id,
                error=str(e)
            )
            return create_error_response(task, str(e))

    def get_task(self, task_id: str) -> Optional[A2ATask]:
        """Kaydedilmiş task'ı döndürür."""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> Dict[str, A2ATask]:
        """Tüm task'ları döndürür."""
        return self._tasks.copy()


def create_a2a_app(
    agent_card: AgentCard,
    task_handler: Callable[[A2ATask], A2ATask]
) -> FastAPI:
    """A2A sunucu uygulaması oluşturur."""
    server = A2AServer(agent_card, task_handler)
    return server.app
