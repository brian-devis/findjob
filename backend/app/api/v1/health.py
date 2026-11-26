"""健康检查接口。"""
from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DBSession
from app.schemas.common import ok

router = APIRouter()


@router.get("/healthz")
async def readiness(session: DBSession) -> dict:
    await session.execute(text("SELECT 1"))
    return ok({"status": "ok"})
