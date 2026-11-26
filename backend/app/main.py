"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.exceptions import AppError
from app.core.logging import get_logger, setup_logging
from app.core.security import hash_password
from app.repositories.admin import AdminRepository
from app.services.scheduler import TaskScheduler
from app.ws import WS_CLOSE_GOING_AWAY, ws_manager, ws_router

setup_logging()
logger = get_logger("app.main")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    session_factory = getattr(app.state, "session_factory", None) or async_session_factory
    if settings.admin_username and settings.admin_password:
        async with session_factory() as session:
            repo = AdminRepository(session)
            if await repo.get_by_username(settings.admin_username) is None:
                await repo.create(
                    settings.admin_username, hash_password(settings.admin_password)
                )
                await session.commit()
                logger.info("已引导创建管理员 %s", settings.admin_username)

    scheduler = TaskScheduler(
        session_factory=session_factory,
        ws_manager=ws_manager,
        poll_interval_seconds=settings.scheduler_poll_interval_seconds,
        dispatch_lease_seconds=settings.task_dispatch_lease_seconds,
    )
    app.state.scheduler = scheduler
    if settings.scheduler_enabled:
        await scheduler.start()

    try:
        yield
    finally:
        await scheduler.stop()
        await ws_manager.close_all(code=WS_CLOSE_GOING_AWAY, reason="server shutdown")


app = FastAPI(
    title=settings.app_name,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'",
    )
    return response


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
        content={
            "code": 1422,
            "message": "请求参数校验失败",
            "data": jsonable_encoder(exc.errors()),
        },
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
app.include_router(ws_router)


def _resolve_static_dir() -> Path | None:
    if settings.static_dir:
        candidate = Path(settings.static_dir)
        return candidate if (candidate / "index.html").is_file() else None
    default_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return default_dist if (default_dist / "index.html").is_file() else None


def mount_frontend(target_app: FastAPI, static_dir: Path) -> None:
    """挂载 React 构建产物（不引入 Nginx），并启用 SPA history fallback。"""
    resolved_root = static_dir.resolve()
    index_file = resolved_root / "index.html"
    assets_dir = resolved_root / "assets"
    if assets_dir.is_dir():
        target_app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

    @target_app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith(("api/", "ws/")) or full_path in ("api", "ws", "healthz"):
            return JSONResponse(
                status_code=404,
                content={"code": 1404, "message": "资源不存在", "data": None},
            )
        candidate = (resolved_root / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(resolved_root)
        ):
            return FileResponse(candidate)
        return FileResponse(index_file)


_detected_static = _resolve_static_dir()
if _detected_static is not None:
    mount_frontend(app, _detected_static)
    logger.info("已启用前端静态托管：%s", _detected_static)
