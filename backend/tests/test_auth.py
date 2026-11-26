"""认证测试。"""
import pytest
from httpx import AsyncClient


async def test_login_wrong_password(client: AsyncClient, session_factory):
    from tests.conftest import create_admin

    await create_admin(session_factory)
    resp = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert resp.status_code == 401


async def test_unauthenticated_access(client: AsyncClient):
    resp = await client.get("/api/agents")
    assert resp.status_code == 401


async def test_login_ok_and_access(auth):
    c: AsyncClient = auth["client"]
    csrf = auth["csrf"]

    # 登录后可访问受保护接口
    resp = await c.get("/api/agents")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0

    # /api/auth/me 返回当前管理员
    resp = await c.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "admin"

    # 状态变更需 CSRF 头
    resp = await c.post("/api/agents", json={"name": "a1"})
    assert resp.status_code == 403  # 缺 CSRF 头

    resp = await c.post("/api/agents", json={"name": "a1"}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    assert resp.json()["data"]["agent_id"]


async def test_logout_invalidates(client: AsyncClient, auth):
    c: AsyncClient = auth["client"]
    csrf = auth["csrf"]

    resp = await c.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200

    # 注销后 refresh 已吊销，访问 access 也因 token_version 变化而失效
    resp = await c.get("/api/agents")
    assert resp.status_code == 401


async def test_refresh_regenerates_csrf_cookie(auth):
    c: AsyncClient = auth["client"]

    # 删除 csrf cookie，模拟刷新时 cookie 缺失
    c.cookies.delete("csrf_token")

    resp = await c.post("/api/auth/refresh")
    assert resp.status_code == 200
    csrf = resp.json()["data"]["csrf_token"]
    assert csrf

    # 缺失时重新生成，必须同步下发 cookie 且与返回值一致
    assert c.cookies.get("csrf_token") == csrf

    # 后续带 CSRF 的变更请求应能通过校验
    resp = await c.post(
        "/api/agents", json={"name": "r1"}, headers={"X-CSRF-Token": csrf}
    )
    assert resp.status_code == 200


async def test_malformed_sub_returns_unauthorized(session):
    import jwt as pyjwt

    from app.core.config import get_settings
    from app.core.exceptions import UnauthorizedError
    from app.services.auth_service import AuthService

    settings = get_settings()
    token = pyjwt.encode(
        {"sub": "no-colon-here", "type": "access", "ver": 0},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    service = AuthService(session)
    with pytest.raises(UnauthorizedError):
        await service.load_admin_from_access(token)
