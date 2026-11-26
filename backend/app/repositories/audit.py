"""审计日志数据访问。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        detail: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor=actor,
            action=action,
            target=target,
            detail=detail or {},
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        action: str | None = None,
        actor: str | None = None,
    ) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.ts.desc(), AuditLog.id.desc())
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if actor:
            stmt = stmt.where(AuditLog.actor == actor)
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        *,
        action: str | None = None,
        actor: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(AuditLog)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if actor:
            stmt = stmt.where(AuditLog.actor == actor)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
