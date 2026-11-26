"""Agent 数据访问。"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent


class AgentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_agent_id(self, agent_id: str) -> Agent | None:
        result = await self._session.execute(
            select(Agent).where(Agent.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self, agent_id: str, name: str, secret_hash: str, secret_version: int = 1
    ) -> Agent:
        agent = Agent(
            agent_id=agent_id,
            name=name,
            secret_hash=secret_hash,
            secret_version=secret_version,
        )
        self._session.add(agent)
        await self._session.flush()
        return agent

    async def list(self, offset: int = 0, limit: int = 50) -> list[Agent]:
        result = await self._session.execute(
            select(Agent).order_by(Agent.created_at).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(Agent))
        return int(result.scalar_one())

    async def delete(self, agent: Agent) -> None:
        await self._session.delete(agent)
        await self._session.flush()
