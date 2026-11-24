"""Agent 服务：注册、轮换、吊销。"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AgentStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import generate_agent_secret, generate_uuid, hash_password
from app.core.time import utcnow
from app.models.agent import Agent
from app.repositories.agent import AgentRepository


class AgentService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = AgentRepository(session)

    async def register(self, name: str) -> tuple[Agent, str]:
        agent_id = generate_uuid()
        secret = generate_agent_secret()
        agent = await self._repo.create(
            agent_id=agent_id,
            name=name,
            secret_hash=hash_password(secret),
            secret_version=1,
        )
        return agent, secret

    async def list(self, offset: int = 0, limit: int = 50) -> list[Agent]:
        return await self._repo.list(offset=offset, limit=limit)

    async def count(self) -> int:
        return await self._repo.count()

    async def get(self, agent_id: str) -> Agent:
        agent = await self._repo.get_by_agent_id(agent_id)
        if agent is None:
            raise NotFoundError("Agent 不存在")
        return agent

    async def rotate_secret(self, agent_id: str) -> tuple[Agent, str]:
        agent = await self.get(agent_id)
        secret = generate_agent_secret()
        agent.secret_hash = hash_password(secret)
        agent.secret_version += 1
        await self._session.flush()
        return agent, secret

    async def revoke(self, agent_id: str, reason: str = "") -> Agent:
        agent = await self.get(agent_id)
        if agent.status == AgentStatus.REVOKED.value:
            raise ConflictError("Agent 已吊销")
        agent.status = AgentStatus.REVOKED.value
        agent.revoked_at = utcnow()
        agent.revoked_reason = reason or None
        await self._session.flush()
        return agent

    async def delete(self, agent_id: str) -> None:
        agent = await self.get(agent_id)
        await self._repo.delete(agent)
