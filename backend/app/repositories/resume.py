"""简历数据访问。"""
from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume import Resume


class ResumeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, resume_id: int) -> Resume | None:
        result = await self._session.execute(select(Resume).where(Resume.id == resume_id))
        return result.scalar_one_or_none()

    async def get_active(self) -> Resume | None:
        result = await self._session.execute(
            select(Resume).where(Resume.is_active.is_(True)).limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        title: str,
        target_role: str | None,
        source_filename: str | None,
        source_format: str,
        raw_content: str,
        structured_json: dict | None = None,
        parent_id: int | None = None,
        is_active: bool = False,
    ) -> Resume:
        resume = Resume(
            title=title,
            target_role=target_role,
            source_filename=source_filename,
            source_format=source_format,
            raw_content=raw_content,
            structured_json=structured_json or {},
            parent_id=parent_id,
            is_active=is_active,
        )
        self._session.add(resume)
        await self._session.flush()
        return resume

    async def clear_active(self) -> None:
        await self._session.execute(update(Resume).values(is_active=False))
        await self._session.flush()

    async def list(self, offset: int = 0, limit: int = 50) -> list[Resume]:
        result = await self._session.execute(
            select(Resume)
            .order_by(Resume.is_active.desc(), Resume.updated_at.desc(), Resume.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(Resume))
        return int(result.scalar_one())

    async def delete(self, resume: Resume) -> None:
        await self._session.delete(resume)
        await self._session.flush()
