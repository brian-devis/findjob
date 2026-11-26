"""认证接口：登录、刷新、注销。"""
from fastapi import APIRouter, Request, Response

from app.api.deps import CSRFRequired, CurrentAdmin, DBSession
from app.core.config import get_settings
from app.core.constants import COOKIE_ACCESS, COOKIE_CSRF, COOKIE_REFRESH
from app.schemas.auth import LoginRequest
from app.schemas.common import ok
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService

router = APIRouter()

settings = get_settings()


def _set_auth_cookies(response: Response, access: str, refresh: str, csrf: str) -> None:
    response.set_cookie(
        COOKIE_ACCESS,
        access,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
    response.set_cookie(
        COOKIE_REFRESH,
        refresh,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/api/auth",
    )
    response.set_cookie(
        COOKIE_CSRF,
        csrf,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


@router.post("/login")
async def login(body: LoginRequest, response: Response, session: DBSession) -> dict:
    service = AuthService(session)
    admin = await service.authenticate(body.username, body.password)
    access, refresh = service.issue_tokens(admin)
    csrf = service.generate_csrf_token()
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="auth.login",
        target=admin.username,
    )
    await session.commit()
    _set_auth_cookies(response, access, refresh, csrf)
    return ok({"username": admin.username, "csrf_token": csrf})


@router.post("/refresh")
async def refresh(request: Request, response: Response, session: DBSession) -> dict:
    token = request.cookies.get(COOKIE_REFRESH)
    service = AuthService(session)
    admin, access = await service.refresh_access(token or "")
    existing_csrf = request.cookies.get(COOKIE_CSRF)
    if existing_csrf:
        csrf = existing_csrf
    else:
        csrf = service.generate_csrf_token()
        response.set_cookie(
            COOKIE_CSRF,
            csrf,
            max_age=settings.refresh_token_expire_days * 86400,
            httponly=False,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
        )
    response.set_cookie(
        COOKIE_ACCESS,
        access,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
    return ok({"username": admin.username, "csrf_token": csrf})


@router.get("/me")
async def me(admin: CurrentAdmin) -> dict:
    return ok({"id": admin.id, "username": admin.username})


@router.post("/logout")
async def logout(response: Response, session: DBSession, _: CSRFRequired, admin: CurrentAdmin) -> dict:
    await AuthService(session).revoke_all(admin)
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="auth.logout",
        target=admin.username,
    )
    await session.commit()
    response.delete_cookie(COOKIE_ACCESS)
    response.delete_cookie(COOKIE_REFRESH, path="/api/auth")
    response.delete_cookie(COOKIE_CSRF)
    return ok()
