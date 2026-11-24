"""Task 数据访问。"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
