"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.exceptions import AppError
from app.core.logging import get_logger, setup_logging
from app.core.security import hash_password
from app.repositories.admin import AdminRepository

setup_logging()
logger = get_logger("app.main")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.admin_username and settings.admin_password:
        async with async_session_factory() as session:
            repo = AdminRepository(session)
            if await repo.get_by_username(settings.admin_username) is None:
                await repo.create(
                    settings.admin_username, hash_password(settings.admin_password)
                )
                await session.commit()
                logger.info("已引导创建管理员 %s", settings.admin_username)
    yield


app = FastAPI(
    title=settings.app_name,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"code": 1422, "message": "请求参数校验失败", "data": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"code": 1500, "message": "服务器内部错误", "data": None},
    )


@app.get("/healthz", tags=["health"])
async def liveness() -> dict:
    return {"code": 0, "message": "success", "data": {"status": "ok"}}


app.include_router(api_router, prefix=settings.api_prefix)
