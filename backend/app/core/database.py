"""数据库连接与会话管理。

选型：SQLAlchemy 2.x 异步 + aiosqlite。
理由（见 docs/database.md）：
- FastAPI 为异步框架，异步引擎避免阻塞事件循环；
- 后续 P2 的 WebSocket 亦为异步，保持统一；
- SQLite 为单写者，采用 NullPool 避免跨线程连接复用导致的锁竞争；
- WAL + busy_timeout + foreign_keys 在连接建立时通过 PRAGMA 设置。
"""
from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    poolclass=NullPool,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：提供数据库会话。"""
    async with async_session_factory() as session:
        yield session
