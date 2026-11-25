"""FastAPI 前端静态托管与安全响应头测试。"""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import mount_frontend, security_headers_middleware


@pytest.mark.asyncio
async def test_static_spa_hosting_and_security_headers(tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>AIJob UI</body></html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('ok');", encoding="utf-8")

    test_app = FastAPI()
    test_app.middleware("http")(security_headers_middleware)

    @test_app.get("/healthz")
    async def healthz():
        return {"code": 0, "data": {"status": "ok"}}

    mount_frontend(test_app, dist)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 根路径返回 index.html + 安全头
        r_root = await client.get("/")
        assert r_root.status_code == 200
        assert "AIJob UI" in r_root.text
        assert r_root.headers["x-content-type-options"] == "nosniff"
        assert r_root.headers["x-frame-options"] == "DENY"
        assert "content-security-policy" in r_root.headers

        # 静态资源正常返回
        r_asset = await client.get("/assets/app.js")
        assert r_asset.status_code == 200
        assert "console.log" in r_asset.text

        # 前端路由 fallback 到 index.html
        r_spa = await client.get("/tasks/123")
        assert r_spa.status_code == 200
        assert "AIJob UI" in r_spa.text

        # /api 未命中路径不返回 index.html，返回 404 JSON
        r_api = await client.get("/api/non-existent")
        assert r_api.status_code == 404
        assert r_api.json()["code"] == 1404
