"""
Queue Worker - Kuyruktan task'ları alıp işler.
"""
import asyncio
from typing import Callable, Dict, Optional
import structlog

from a2a.protocol import A2ATask, TaskStatus
from .task_queue import TaskQueue

logger = structlog.get_logger()


class QueueWorker:
    """
    Kuyruk işçisi - belirli bir kuyruktan task'ları alıp işler.
    """

    def __init__(
        self,
        queue: TaskQueue,
        task_handler: Callable[[A2ATask], A2ATask],
        queue_name: str = "default",
        poll_interval: float = 0.5,
        max_concurrent: int = 5
    ):
        self.queue = queue
        self.task_handler = task_handler
        self.queue_name = queue_name
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent

        self._running = False
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def start(self):
        """Worker'ı başlatır."""
        self._running = True
        logger.info(
            "worker_started",
            queue=self.queue_name,
            max_concurrent=self.max_concurrent
        )

        while self._running:
            try:
                # Kuyruktan task al
                task = await self.queue.dequeue(self.queue_name)

                if task:
                    # Concurrent limit kontrolü
                    await self._semaphore.acquire()

                    # Async olarak işle
                    asyncio_task = asyncio.create_task(self._process_task(task))
                    self._active_tasks[task.task_id] = asyncio_task
                else:
                    # Kuyruk boşsa bekle
                    await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                logger.info("worker_cancelled", queue=self.queue_name)
                break
            except Exception as e:
                logger.error("worker_error", queue=self.queue_name, error=str(e))
                await asyncio.sleep(self.poll_interval)

    async def stop(self):
        """Worker'ı durdurur."""
        self._running = False

        # Aktif task'ları bekle
        if self._active_tasks:
            logger.info(
                "waiting_active_tasks",
                count=len(self._active_tasks)
            )
            await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)

        logger.info("worker_stopped", queue=self.queue_name)

    async def _process_task(self, task: A2ATask):
        """Tek bir task'ı işler."""
        try:
            logger.info(
                "processing_task",
                task_id=task.task_id,
                from_agent=task.from_agent,
                to_agent=task.to_agent
            )

            task.update_status(TaskStatus.WORKING)
            await self.queue.update_task(task)

            # Handler'ı çağır
            if asyncio.iscoroutinefunction(self.task_handler):
                result = await self.task_handler(task)
            else:
                result = self.task_handler(task)

            # Sonucu güncelle
            await self.queue.update_task(result)

            logger.info(
                "task_completed",
                task_id=task.task_id,
                status=result.status
            )

        except Exception as e:
            logger.error(
                "task_processing_error",
                task_id=task.task_id,
                error=str(e)
            )
            task.update_status(TaskStatus.FAILED, error=str(e))
            await self.queue.update_task(task)

        finally:
            # Cleanup
            self._semaphore.release()
            if task.task_id in self._active_tasks:
                del self._active_tasks[task.task_id]

    @property
    def active_count(self) -> int:
        """Aktif task sayısı."""
        return len(self._active_tasks)

    @property
    def is_running(self) -> bool:
        """Worker çalışıyor mu?"""
        return self._running


class MultiQueueWorker:
    """
    Birden fazla kuyruğu dinleyen worker.
    Her departman için ayrı kuyruk olduğunda kullanılır.
    """

    def __init__(
        self,
        queue: TaskQueue,
        handlers: Dict[str, Callable[[A2ATask], A2ATask]],
        poll_interval: float = 0.5,
        max_concurrent_per_queue: int = 3
    ):
        self.queue = queue
        self.handlers = handlers  # queue_name -> handler
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent_per_queue

        self._workers: Dict[str, QueueWorker] = {}
        self._running = False

    async def start(self):
        """Tüm worker'ları başlatır."""
        self._running = True

        for queue_name, handler in self.handlers.items():
            worker = QueueWorker(
                queue=self.queue,
                task_handler=handler,
                queue_name=queue_name,
                poll_interval=self.poll_interval,
                max_concurrent=self.max_concurrent
            )
            self._workers[queue_name] = worker

        # Tüm worker'ları paralel başlat
        await asyncio.gather(*[
            worker.start() for worker in self._workers.values()
        ])

    async def stop(self):
        """Tüm worker'ları durdurur."""
        self._running = False

        await asyncio.gather(*[
            worker.stop() for worker in self._workers.values()
        ])

        logger.info("multi_queue_worker_stopped")

    def get_stats(self) -> Dict[str, int]:
        """Her kuyruk için aktif task sayısı."""
        return {
            queue_name: worker.active_count
            for queue_name, worker in self._workers.items()
        }
