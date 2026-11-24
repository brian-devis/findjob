"""Agent 接口测试。"""
from httpx import AsyncClient


async def _register(client: AsyncClient, csrf: str, name: str = "agent-1") -> dict:
    resp = await client.post(
        "/api/agents", json={"name": name}, headers={"X-CSRF-Token": csrf}
    )
    assert resp.status_code == 200
    return resp.json()["data"]


async def test_register_returns_secret_once(auth):
    c = auth["client"]
    data = await _register(c, auth["csrf"])
    assert data["agent_id"]
    assert data["secret"]

    # 列表不应包含 secret 明文
    resp = await c.get("/api/agents")
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert "secret" not in items[0]


async def test_get_and_rotate_and_revoke(auth):
    c = auth["client"]
    csrf = auth["csrf"]
    data = await _register(c, csrf)
    agent_id = data["agent_id"]

    resp = await c.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "active"

    resp = await c.post(
        f"/api/agents/{agent_id}/rotate-secret", headers={"X-CSRF-Token": csrf}
    )
    assert resp.status_code == 200
    new_secret = resp.json()["data"]["secret"]
    assert new_secret and new_secret != data["secret"]

    resp = await c.post(
        f"/api/agents/{agent_id}/revoke", headers={"X-CSRF-Token": csrf}
    )
    assert resp.json()["data"]["status"] == "revoked"


async def test_delete(auth):
    c = auth["client"]
    csrf = auth["csrf"]
    data = await _register(c, csrf)
    agent_id = data["agent_id"]

    resp = await c.delete(f"/api/agents/{agent_id}", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200

    resp = await c.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 404
