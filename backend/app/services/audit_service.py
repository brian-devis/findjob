"""审计日志服务：记录关键操作并防御性剔除敏感键。"""
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.repositories.audit import AuditLogRepository

_SENSITIVE_KEYWORDS = ("password", "secret", "token", "api_key", "apikey", "authorization")


def _sanitize_detail(detail: dict[str, Any] | None) -> dict[str, Any]:
    if not detail:
        return {}
    clean: dict[str, Any] = {}
    for k, v in detail.items():
        lowered = str(k).lower()
        if any(word in lowered for word in _SENSITIVE_KEYWORDS):
            continue
        if isinstance(v, dict):
            clean[k] = _sanitize_detail(v)
        else:
            clean[k] = v
    return clean


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuditLogRepository(session)

    async def record(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        detail: dict[str, Any] | None = None,
    ) -> AuditLog:
        return await self._repo.create(
            actor=actor[:64],
            action=action[:64],
            target=target[:128],
            detail=_sanitize_detail(detail),
        )

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        action: str | None = None,
        actor: str | None = None,
    ) -> list[AuditLog]:
        return await self._repo.list(offset=offset, limit=limit, action=action, actor=actor)

    async def count(
        self,
        *,
        action: str | None = None,
        actor: str | None = None,
    ) -> int:
        return await self._repo.count(action=action, actor=actor)
