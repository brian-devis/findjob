"""pytest fixtures。"""
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.repositories.admin import AdminRepository


@pytest_asyncio.fixture
async def engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def client(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def create_admin(session_factory, username: str = "admin", password: str = "secret") -> None:
    async with session_factory() as s:
        repo = AdminRepository(s)
        if await repo.get_by_username(username) is None:
            await repo.create(username, hash_password(password))
            await s.commit()


@pytest_asyncio.fixture
async def auth(client, session_factory):
    """创建管理员并登录，返回带认证与 CSRF 的辅助对象。"""
    await create_admin(session_factory)

    resp = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "secret"}
    )
    assert resp.status_code == 200
    body = resp.json()
    csrf = body["data"]["csrf_token"]
    return {"client": client, "csrf": csrf}
