"""任务服务：创建、状态流转（状态机）与幂等。

P0 决策：任务状态以数据库为准；「至少一次投递 + task_id 幂等」在服务端
落地为基础，Agent 本地持久化执行记录（真正的恰好一次）留待 P3。
"""
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TaskStatus, TaskType
from app.core.exceptions import InvalidStateError, NotFoundError, ValidationError
from app.core.security import generate_uuid
from app.core.time import utcnow
from app.models.task import Task
from app.repositories.task import TaskRepository

# 显式维护允许通过 REST/业务服务创建的任务类型白名单
_ALLOWED_TYPES = {
    TaskType.PING,
    TaskType.SYSTEM_INFO,
    TaskType.BOSS_CHECK_LOGIN,
    TaskType.BOSS_SYNC_RESUME,
    TaskType.BOSS_SCAN_JOBS,
    TaskType.BOSS_APPLY_JOB,
}

# 状态机：from -> 允许的 to
_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.QUEUED: {TaskStatus.DISPATCHED, TaskStatus.CANCELLED},
    TaskStatus.DISPATCHED: {TaskStatus.RUNNING, TaskStatus.QUEUED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.QUEUED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.FAILED: set(),  # 终态，不可再流转
    TaskStatus.SUCCEEDED: set(),
    TaskStatus.CANCELLED: set(),
}

_TERMINAL = {TaskStatus.SUCCEEDED, TaskStatus.CANCELLED, TaskStatus.FAILED}


class TaskService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = TaskRepository(session)

    # ---- 创建 ----
    async def create(
        self,
        *,
        type_: TaskType,
        agent_id: str | None,
        payload: dict[str, Any],
        priority: int,
        max_attempts: int,
        timeout_seconds: int,
        idempotency_key: str | None = None,
        scheduled_at=None,
    ) -> Task:
        if type_ not in _ALLOWED_TYPES:
            raise ValidationError(f"任务类型 {type_.value} 暂不支持")

        if idempotency_key:
            existing = await self._repo.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing

        task = await self._repo.create(
            task_id=generate_uuid(),
            agent_id=agent_id,
            type=type_.value,
            status=TaskStatus.QUEUED.value,
            payload=payload or {},
            priority=priority,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
            idempotency_key=idempotency_key,
            scheduled_at=scheduled_at,
        )
        return task

    # ---- 查询 ----
    async def get(self, task_id: str) -> Task:
        task = await self._repo.get_by_task_id(task_id)
        if task is None:
            raise NotFoundError("任务不存在")
        return task

    async def list(self, offset: int = 0, limit: int = 50, status: str | None = None) -> list[Task]:
        return await self._repo.list(offset=offset, limit=limit, status=status)

    async def count(self, status: str | None = None) -> int:
        return await self._repo.count(status=status)

    # ---- 状态流转 ----
    def _assert(self, task: Task, target: TaskStatus) -> None:
        if task.status_enum not in _TRANSITIONS:
            raise InvalidStateError(f"未知状态 {task.status}")
        if target not in _TRANSITIONS[task.status_enum]:
            raise InvalidStateError(f"非法状态流转：{task.status} -> {target.value}")

    async def dispatch(self, task: Task, lease_seconds: int) -> Task:
        self._assert(task, TaskStatus.DISPATCHED)
        task.status = TaskStatus.DISPATCHED.value
        task.dispatched_at = utcnow()
        task.lease_expires_at = utcnow() + timedelta(seconds=lease_seconds)
        await self._session.flush()
        return task

    async def ack(self, task: Task) -> Task:
        self._assert(task, TaskStatus.RUNNING)
        task.status = TaskStatus.RUNNING.value
        task.started_at = utcnow()
        task.lease_expires_at = None
        await self._session.flush()
        return task

    async def complete(
        self,
        task: Task,
        succeeded: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Task:
        if succeeded:
            self._assert(task, TaskStatus.SUCCEEDED)
            task.status = TaskStatus.SUCCEEDED.value
            task.result = result or {}
            task.error = None
            task.finished_at = utcnow()
        else:
            task.attempt += 1
            task.error = error
            if task.attempt < task.max_attempts:
                target = TaskStatus.QUEUED  # 重试：回到队列
                self._assert(task, target)
                task.status = target.value
                task.result = None
                task.lease_expires_at = None
                task.dispatched_at = None
                task.started_at = None
            else:
                target = TaskStatus.FAILED
                self._assert(task, target)
                task.status = target.value
                task.finished_at = utcnow()
        await self._session.flush()
        return task

    async def cancel(self, task: Task) -> Task:
        self._assert(task, TaskStatus.CANCELLED)
        task.status = TaskStatus.CANCELLED.value
        task.finished_at = utcnow()
        await self._session.flush()
        return task

    async def requeue_expired(self, task: Task) -> Task:
        self._assert(task, TaskStatus.QUEUED)
        task.status = TaskStatus.QUEUED.value
        task.lease_expires_at = None
        task.dispatched_at = None
        await self._session.flush()
        return task

    def is_terminal(self, task: Task) -> bool:
        return task.status_enum in _TERMINAL
