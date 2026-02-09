"""
Task Queue - Agent isteklerinin kuyruklanması.

Redis varsa Redis kullanır, yoksa in-memory kuyruk kullanır.
"""
import asyncio
import json
from abc import ABC, abstractmethod
from collections import deque
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import structlog

from a2a.protocol import A2ATask, TaskStatus

logger = structlog.get_logger()


class TaskQueue(ABC):
    """Task kuyruğu için abstract base class."""

    @abstractmethod
    async def enqueue(self, task: A2ATask, priority: int = 1) -> str:
        """Task'ı kuyruğa ekler. Task ID döndürür."""
        pass

    @abstractmethod
    async def dequeue(self, queue_name: str = "default") -> Optional[A2ATask]:
        """Kuyruktan bir task alır."""
        pass

    @abstractmethod
    async def peek(self, queue_name: str = "default") -> Optional[A2ATask]:
        """Kuyruktaki ilk task'a bakar (çıkarmaz)."""
        pass

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[A2ATask]:
        """Task ID'ye göre task döndürür."""
        pass

    @abstractmethod
    async def update_task(self, task: A2ATask) -> bool:
        """Task'ı günceller."""
        pass

    @abstractmethod
    async def get_queue_length(self, queue_name: str = "default") -> int:
        """Kuyruk uzunluğunu döndürür."""
        pass

    @abstractmethod
    async def get_pending_tasks(self, queue_name: str = "default") -> List[A2ATask]:
        """Bekleyen tüm task'ları döndürür."""
        pass


class InMemoryQueue(TaskQueue):
    """
    In-memory task kuyruğu.
    Redis yoksa veya test için kullanılır.
    """

    def __init__(self):
        # queue_name -> deque of (priority, timestamp, task)
        self._queues: Dict[str, deque] = {}
        self._tasks: Dict[str, A2ATask] = {}
        self._lock = asyncio.Lock()

    def _get_queue(self, queue_name: str) -> deque:
        """Kuyruk yoksa oluşturur."""
        if queue_name not in self._queues:
            self._queues[queue_name] = deque()
        return self._queues[queue_name]

    async def enqueue(self, task: A2ATask, priority: int = 1, queue_name: str = "default") -> str:
        """Task'ı kuyruğa ekler."""
        async with self._lock:
            queue = self._get_queue(queue_name)
            timestamp = datetime.utcnow().isoformat()

            # Priority'ye göre sıralı ekle (yüksek priority önce)
            item = (priority, timestamp, task.task_id)

            # Basit insertion sort
            inserted = False
            for i, (p, t, tid) in enumerate(queue):
                if priority > p:
                    queue.insert(i, item)
                    inserted = True
                    break

            if not inserted:
                queue.append(item)

            self._tasks[task.task_id] = task

            logger.info(
                "task_enqueued",
                task_id=task.task_id,
                queue=queue_name,
                priority=priority,
                queue_length=len(queue)
            )

            return task.task_id

    async def dequeue(self, queue_name: str = "default") -> Optional[A2ATask]:
        """Kuyruktan bir task alır."""
        async with self._lock:
            queue = self._get_queue(queue_name)

            if not queue:
                return None

            _, _, task_id = queue.popleft()
            task = self._tasks.get(task_id)

            if task:
                logger.info(
                    "task_dequeued",
                    task_id=task_id,
                    queue=queue_name,
                    remaining=len(queue)
                )

            return task

    async def peek(self, queue_name: str = "default") -> Optional[A2ATask]:
        """Kuyruktaki ilk task'a bakar."""
        async with self._lock:
            queue = self._get_queue(queue_name)

            if not queue:
                return None

            _, _, task_id = queue[0]
            return self._tasks.get(task_id)

    async def get_task(self, task_id: str) -> Optional[A2ATask]:
        """Task ID'ye göre task döndürür."""
        return self._tasks.get(task_id)

    async def update_task(self, task: A2ATask) -> bool:
        """Task'ı günceller."""
        if task.task_id in self._tasks:
            self._tasks[task.task_id] = task
            return True
        return False

    async def get_queue_length(self, queue_name: str = "default") -> int:
        """Kuyruk uzunluğunu döndürür."""
        return len(self._get_queue(queue_name))

    async def get_pending_tasks(self, queue_name: str = "default") -> List[A2ATask]:
        """Bekleyen tüm task'ları döndürür."""
        queue = self._get_queue(queue_name)
        tasks = []
        for _, _, task_id in queue:
            task = self._tasks.get(task_id)
            if task:
                tasks.append(task)
        return tasks

    async def clear(self, queue_name: str = "default"):
        """Kuyruğu temizler."""
        async with self._lock:
            if queue_name in self._queues:
                self._queues[queue_name].clear()


class RedisQueue(TaskQueue):
    """
    Redis tabanlı task kuyruğu.
    Production ortamı için önerilir.
    """

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.host = host
        self.port = port
        self.db = db
        self._redis = None
        self._connected = False

    async def connect(self):
        """Redis'e bağlanır."""
        try:
            import redis.asyncio as redis
            self._redis = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True
            )
            await self._redis.ping()
            self._connected = True
            logger.info("redis_connected", host=self.host, port=self.port)
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            self._connected = False
            raise

    async def disconnect(self):
        """Redis bağlantısını kapatır."""
        if self._redis:
            await self._redis.close()
            self._connected = False

    def _queue_key(self, queue_name: str) -> str:
        return f"a2a:queue:{queue_name}"

    def _task_key(self, task_id: str) -> str:
        return f"a2a:task:{task_id}"

    async def enqueue(self, task: A2ATask, priority: int = 1, queue_name: str = "default") -> str:
        """Task'ı Redis kuyruğuna ekler."""
        if not self._connected:
            await self.connect()

        # Task'ı kaydet
        await self._redis.set(
            self._task_key(task.task_id),
            task.model_dump_json()
        )

        # Sorted set'e ekle (score = priority * -1 for descending order)
        await self._redis.zadd(
            self._queue_key(queue_name),
            {task.task_id: -priority}
        )

        logger.info(
            "task_enqueued_redis",
            task_id=task.task_id,
            queue=queue_name,
            priority=priority
        )

        return task.task_id

    async def dequeue(self, queue_name: str = "default") -> Optional[A2ATask]:
        """Redis kuyruğundan task alır."""
        if not self._connected:
            await self.connect()

        # En yüksek priority'li task'ı al ve kaldır
        result = await self._redis.zpopmin(self._queue_key(queue_name))

        if not result:
            return None

        task_id, _ = result[0]

        # Task verilerini al
        task_data = await self._redis.get(self._task_key(task_id))
        if task_data:
            return A2ATask.model_validate_json(task_data)

        return None

    async def peek(self, queue_name: str = "default") -> Optional[A2ATask]:
        """Kuyruktaki ilk task'a bakar."""
        if not self._connected:
            await self.connect()

        result = await self._redis.zrange(self._queue_key(queue_name), 0, 0)

        if not result:
            return None

        task_id = result[0]
        task_data = await self._redis.get(self._task_key(task_id))

        if task_data:
            return A2ATask.model_validate_json(task_data)

        return None

    async def get_task(self, task_id: str) -> Optional[A2ATask]:
        """Task ID'ye göre task döndürür."""
        if not self._connected:
            await self.connect()

        task_data = await self._redis.get(self._task_key(task_id))
        if task_data:
            return A2ATask.model_validate_json(task_data)
        return None

    async def update_task(self, task: A2ATask) -> bool:
        """Task'ı günceller."""
        if not self._connected:
            await self.connect()

        result = await self._redis.set(
            self._task_key(task.task_id),
            task.model_dump_json()
        )
        return result is not None

    async def get_queue_length(self, queue_name: str = "default") -> int:
        """Kuyruk uzunluğunu döndürür."""
        if not self._connected:
            await self.connect()

        return await self._redis.zcard(self._queue_key(queue_name))

    async def get_pending_tasks(self, queue_name: str = "default") -> List[A2ATask]:
        """Bekleyen tüm task'ları döndürür."""
        if not self._connected:
            await self.connect()

        task_ids = await self._redis.zrange(self._queue_key(queue_name), 0, -1)
        tasks = []

        for task_id in task_ids:
            task = await self.get_task(task_id)
            if task:
                tasks.append(task)

        return tasks


# Factory function
_queue_instance: Optional[TaskQueue] = None


async def get_queue(use_redis: bool = False, **kwargs) -> TaskQueue:
    """
    Task kuyruğu instance'ı döndürür.
    Singleton pattern kullanır.
    """
    global _queue_instance

    if _queue_instance is not None:
        return _queue_instance

    if use_redis:
        try:
            _queue_instance = RedisQueue(**kwargs)
            await _queue_instance.connect()
            logger.info("using_redis_queue")
        except Exception as e:
            logger.warning("redis_fallback_to_memory", error=str(e))
            _queue_instance = InMemoryQueue()
    else:
        _queue_instance = InMemoryQueue()
        logger.info("using_memory_queue")

    return _queue_instance
