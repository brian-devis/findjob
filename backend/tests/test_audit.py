"""审计日志测试：敏感字段脱敏、关键操作自动入库与查询过滤。"""
import pytest

from app.services.audit_service import AuditService


@pytest.mark.asyncio
async def test_audit_service_sanitizes_sensitive_keys(session):
    svc = AuditService(session)
    entry = await svc.record(
        actor="admin:root",
        action="provider.create",
        target="1",
        detail={
            "name": "deepseek",
            "api_key": "sk-must-not-appear",
            "nested": {"secret_token": "leak", "safe": "ok"},
            "password": "pwd",
        },
    )
    await session.commit()

    assert entry.detail == {"name": "deepseek", "nested": {"safe": "ok"}}
    assert "sk-must-not-appear" not in str(entry.detail)


@pytest.mark.asyncio
async def test_audit_logs_recorded_across_endpoints(auth):
    c = auth["client"]
    csrf = auth["csrf"]
    headers = {"X-CSRF-Token": csrf}

    # 注册 Agent、轮换密钥、创建任务、取消任务、创建并更新/删除 Provider
    r_agent = await c.post("/api/agents", json={"name": "audit-agent"}, headers=headers)
    assert r_agent.status_code == 200
    agent_id = r_agent.json()["data"]["agent_id"]
    agent_secret = r_agent.json()["data"]["secret"]

    r_rot = await c.post(f"/api/agents/{agent_id}/rotate-secret", headers=headers)
    assert r_rot.status_code == 200

    r_task = await c.post(
        "/api/tasks",
        json={"type": "PING", "agent_id": agent_id, "payload": {"k": "v"}},
        headers=headers,
    )
    assert r_task.status_code == 200
    task_id = r_task.json()["data"]["task_id"]

    r_cancel = await c.post(f"/api/tasks/{task_id}/cancel", headers=headers)
    assert r_cancel.status_code == 200

    secret_key = "sk-provider-secret-do-not-log"
    r_prov = await c.post(
        "/api/providers",
        json={
            "name": "audit-p",
            "base_url": "https://api.example.com/v1",
            "api_format": "openai",
            "model": "m1",
            "api_key": secret_key,
        },
        headers=headers,
    )
    assert r_prov.status_code == 200
    prov_id = r_prov.json()["data"]["id"]

    r_patch = await c.patch(
        f"/api/providers/{prov_id}",
        json={"enabled": False, "api_key": "sk-new-secret-do-not-log"},
        headers=headers,
    )
    assert r_patch.status_code == 200

    r_del = await c.delete(f"/api/providers/{prov_id}", headers=headers)
    assert r_del.status_code == 200

    # 查询全量审计日志，校验动作覆盖与绝无明文密钥
    r_logs = await c.get("/api/audit-logs?limit=50")
    assert r_logs.status_code == 200
    assert agent_secret not in r_logs.text
    assert secret_key not in r_logs.text
    assert "sk-new-secret-do-not-log" not in r_logs.text

    items = r_logs.json()["data"]["items"]
    actions = {item["action"] for item in items}
    expected = {
        "auth.login",
        "agent.register",
        "agent.rotate_secret",
        "task.create",
        "task.cancel",
        "provider.create",
        "provider.update",
        "provider.delete",
    }
    assert expected.issubset(actions)

    # 按 action 过滤
    r_filtered = await c.get("/api/audit-logs?action=provider.update")
    assert r_filtered.status_code == 200
    f_data = r_filtered.json()["data"]
    assert f_data["total"] == 1
    assert f_data["items"][0]["detail"]["key_updated"] is True
