"""AI Provider 数据访问。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_provider import AIProvider


class AIProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, provider_id: int) -> AIProvider | None:
        result = await self._session.execute(
            select(AIProvider).where(AIProvider.id == provider_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> AIProvider | None:
        result = await self._session.execute(
            select(AIProvider).where(AIProvider.name == name)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        name: str,
        base_url: str,
        api_format: str,
        model: str,
        api_key_enc: str | None,
        enabled: bool,
    ) -> AIProvider:
        provider = AIProvider(
            name=name,
            base_url=base_url,
            api_format=api_format,
            model=model,
            api_key_enc=api_key_enc,
            enabled=enabled,
        )
        self._session.add(provider)
        await self._session.flush()
        return provider

    async def list(self, offset: int = 0, limit: int = 50) -> list[AIProvider]:
        result = await self._session.execute(
            select(AIProvider).order_by(AIProvider.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(AIProvider))
        return int(result.scalar_one())

    async def delete(self, provider: AIProvider) -> None:
        await self._session.delete(provider)
        await self._session.flush()
