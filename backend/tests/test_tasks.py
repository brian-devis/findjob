"""任务接口测试。"""


async def _create(auth, payload: dict) -> dict:
    c = auth["client"]
    resp = await c.post("/api/tasks", json=payload, headers={"X-CSRF-Token": auth["csrf"]})
    return resp


async def test_create_ping_and_get(auth):
    resp = await _create(auth, {"type": "PING", "payload": {"host": "127.0.0.1"}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "queued"
    assert data["type"] == "PING"

    resp = await auth["client"].get(f"/api/tasks/{data['task_id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["task_id"] == data["task_id"]


async def test_reject_unsupported_type(auth):
    resp = await _create(auth, {"type": "RUN_SOMETHING"})
    assert resp.status_code == 422  # Pydantic 枚举校验失败


async def test_idempotency_dedup(auth):
    key = "idem-001"
    resp = await _create(auth, {"type": "SYSTEM_INFO", "idempotency_key": key})
    first = resp.json()["data"]["task_id"]

    resp = await _create(auth, {"type": "SYSTEM_INFO", "idempotency_key": key})
    second = resp.json()["data"]["task_id"]

    assert first == second


async def test_list_and_cancel(auth):
    await _create(auth, {"type": "PING"})
    resp = await auth["client"].get("/api/tasks")
    assert resp.json()["data"]["total"] >= 1

    task_id = resp.json()["data"]["items"][0]["task_id"]
    resp = await auth["client"].post(
        f"/api/tasks/{task_id}/cancel", headers={"X-CSRF-Token": auth["csrf"]}
    )
    assert resp.json()["data"]["status"] == "cancelled"
