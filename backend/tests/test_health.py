"""健康检查测试。"""
from httpx import AsyncClient


async def test_liveness(client: AsyncClient):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


async def test_readiness(client: AsyncClient):
    resp = await client.get("/api/healthz")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
