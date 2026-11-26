"""Task 数据访问。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TaskStatus
from app.models.task import Task


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_task_id(self, task_id: str) -> Task | None:
        result = await self._session.execute(
            select(Task).where(Task.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, key: str) -> Task | None:
        result = await self._session.execute(
            select(Task).where(Task.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Task:
        task = Task(**kwargs)
        self._session.add(task)
        await self._session.flush()
        return task

    async def list(
        self, offset: int = 0, limit: int = 50, status: str | None = None
    ) -> list[Task]:
        stmt = select(Task).order_by(Task.created_at.desc())
        if status is not None:
            stmt = stmt.where(Task.status == status)
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, status: str | None = None) -> int:
        stmt = select(func.count()).select_from(Task)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_dispatchable(
        self, now: datetime, online_agent_ids: list[str], limit: int = 50
    ) -> list[Task]:
        if not online_agent_ids:
            return []
        stmt = (
            select(Task)
            .where(
                Task.status == TaskStatus.QUEUED.value,
                or_(Task.scheduled_at.is_(None), Task.scheduled_at <= now),
                or_(Task.agent_id.is_(None), Task.agent_id.in_(online_agent_ids)),
            )
            .order_by(Task.priority.desc(), Task.created_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_expired_dispatched(self, now: datetime, limit: int = 50) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.status == TaskStatus.DISPATCHED.value,
                Task.lease_expires_at.is_not(None),
                Task.lease_expires_at <= now,
            )
            .order_by(Task.lease_expires_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_running(self, limit: int = 200) -> list[Task]:
        stmt = (
            select(Task)
            .where(
                Task.status == TaskStatus.RUNNING.value,
                Task.started_at.is_not(None),
            )
            .order_by(Task.started_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def claim_for_dispatch(
        self,
        *,
        task_id: str,
        agent_id: str,
        dispatched_at: datetime,
        lease_expires_at: datetime,
    ) -> bool:
        """原子条件抢占：仅当任务仍为 queued 时转为 dispatched。"""
        result = await self._session.execute(
            update(Task)
            .where(Task.task_id == task_id, Task.status == TaskStatus.QUEUED.value)
            .values(
                status=TaskStatus.DISPATCHED.value,
                agent_id=agent_id,
                dispatched_at=dispatched_at,
                lease_expires_at=lease_expires_at,
            )
        )
        await self._session.flush()
        return (result.rowcount or 0) == 1
