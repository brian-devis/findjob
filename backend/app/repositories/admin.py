"""Admin 数据访问。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import Admin


class AdminRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_username(self, username: str) -> Admin | None:
        result = await self._session.execute(
            select(Admin).where(Admin.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, admin_id: int) -> Admin | None:
        return await self._session.get(Admin, admin_id)

    async def create(self, username: str, password_hash: str) -> Admin:
        admin = Admin(username=username, password_hash=password_hash)
        self._session.add(admin)
        await self._session.flush()
        return admin
