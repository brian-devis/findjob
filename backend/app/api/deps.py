"""FastAPI 依赖。"""
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import COOKIE_ACCESS, COOKIE_CSRF, HEADER_CSRF
from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.models.admin import Admin
from app.services.auth_service import AuthService

DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_admin(request: Request, session: DBSession) -> Admin:
    token = request.cookies.get(COOKIE_ACCESS)
    if not token:
        raise UnauthorizedError("未登录")
    return await AuthService(session).load_admin_from_access(token)


CurrentAdmin = Annotated[Admin, Depends(get_current_admin)]


async def require_csrf(request: Request) -> None:
    header = request.headers.get(HEADER_CSRF)
    cookie = request.cookies.get(COOKIE_CSRF)
    if not header or not cookie or header != cookie:
        raise ForbiddenError("CSRF 校验失败")


CSRFRequired = Annotated[None, Depends(require_csrf)]
