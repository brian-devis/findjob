"""Agent WebSocket 端点集成测试：鉴权、心跳、任务闭环、幂等与管理接口联动。"""
import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.core.database import get_db
from app.core.enums import TaskStatus, TaskType
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.repositories.admin import AdminRepository
from app.services.task_service import TaskService
from app.ws import (
    WS_CLOSE_AGENT_REVOKED,
    WS_CLOSE_AUTH_FAILED,
    WS_CLOSE_PROTOCOL_ERROR,
)


@pytest.fixture
def ws_env(tmp_path, monkeypatch):
    """提供独立 SQLite 文件库与禁用后台自动轮询的 TestClient。"""
    db_path = tmp_path / "ws_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _init_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as s:
            await AdminRepository(s).create("admin", hash_password("secret"))
            await s.commit()

    asyncio.run(_init_db())

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            yield s

    settings = get_settings()
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    app.dependency_overrides[get_db] = override_get_db
    app.state.session_factory = factory

    with TestClient(app) as tc:
        yield {"client": tc, "factory": factory}

    app.dependency_overrides.clear()
    if hasattr(app.state, "session_factory"):
        delattr(app.state, "session_factory")
    asyncio.run(engine.dispose())


def _login(tc: TestClient) -> str:
    resp = tc.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    assert resp.status_code == 200
    return resp.json()["data"]["csrf_token"]


def _register_agent(tc: TestClient, csrf: str, name: str = "win-agent") -> tuple[str, str]:
    resp = tc.post("/api/agents", json={"name": name}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    data = resp.json()["data"]
    return data["agent_id"], data["secret"]


def test_ws_auth_failures_and_revoked(ws_env):
    tc = ws_env["client"]
    csrf = _login(tc)
    agent_id, secret = _register_agent(tc, csrf)

    # 1. 缺少鉴权头 -> 4001
    with tc.websocket_connect("/ws/agent") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "auth_error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_text()
        assert exc_info.value.code == WS_CLOSE_AUTH_FAILED

    # 2. 错误 secret -> 4001
    with tc.websocket_connect(
        "/ws/agent",
        headers={"X-Agent-Id": agent_id, "Authorization": "Bearer wrong-secret"},
    ) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "auth_error"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_text()
        assert exc_info.value.code == WS_CLOSE_AUTH_FAILED

    # 3. 已吊销 Agent -> 4002
    rev = tc.post(f"/api/agents/{agent_id}/revoke", headers={"X-CSRF-Token": csrf})
    assert rev.status_code == 200
    with tc.websocket_connect(
        "/ws/agent",
        headers={"X-Agent-Id": agent_id, "Authorization": f"Bearer {secret}"},
    ) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "auth_error"
        assert msg["data"]["reason"] == "agent revoked"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_text()
        assert exc_info.value.code == WS_CLOSE_AGENT_REVOKED


def test_ws_heartbeat_online_status_and_protocol_error(ws_env):
    tc = ws_env["client"]
    csrf = _login(tc)
    agent_id, secret = _register_agent(tc, csrf)

    headers = {"X-Agent-Id": agent_id, "Authorization": f"Bearer {secret}"}
    with tc.websocket_connect("/ws/agent", headers=headers) as ws:
        auth_ok = ws.receive_json()
        assert auth_ok == {"type": "auth_ok", "data": {"agent_id": agent_id}}

        # 在线状态反映在 REST API
        detail = tc.get(f"/api/agents/{agent_id}").json()["data"]
        assert detail["online"] is True
        assert detail["last_seen_at"] is not None

        # ping -> pong
        ws.send_json({"type": "ping", "id": "p1", "data": {}})
        pong = ws.receive_json()
        assert pong == {"type": "pong", "id": "p1", "data": {}}

        # 未知消息类型 -> error 但不断开
        ws.send_json({"type": "unknown_evt", "id": "u1", "data": {}})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["data"]["code"] == "UNKNOWN_TYPE"

        # 非法 JSON -> error + 4004 关闭
        ws.send_text("{not-json")
        err2 = ws.receive_json()
        assert err2["type"] == "error"
        assert err2["data"]["code"] == "PROTOCOL_ERROR"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_text()
        assert exc_info.value.code == WS_CLOSE_PROTOCOL_ERROR

    # 断开后 online 为 False
    detail_after = tc.get(f"/api/agents/{agent_id}").json()["data"]
    assert detail_after["online"] is False


def test_ws_end_to_end_task_dispatch_ack_result_and_dedup(ws_env):
    tc = ws_env["client"]
    factory = ws_env["factory"]
    csrf = _login(tc)
    agent_id, secret = _register_agent(tc, csrf)

    # 创建任务
    resp = tc.post(
        "/api/tasks",
        json={"type": TaskType.PING.value, "agent_id": agent_id, "payload": {"echo": "hi"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    task_id = resp.json()["data"]["task_id"]

    headers = {"X-Agent-Id": agent_id, "Authorization": f"Bearer {secret}"}
    with tc.websocket_connect("/ws/agent", headers=headers) as ws:
        assert ws.receive_json()["type"] == "auth_ok"

        # 手动触发一次调度周期下发任务
        stats = asyncio.run(app.state.scheduler.run_once())
        assert stats["dispatched"] == 1

        dispatch_msg = ws.receive_json()
        assert dispatch_msg["type"] == "task_dispatch"
        assert dispatch_msg["data"]["task_id"] == task_id
        assert dispatch_msg["data"]["payload"] == {"echo": "hi"}

        # 发送 task_ack -> running
        ws.send_json({"type": "task_ack", "data": {"task_id": task_id}})
        # 用一次 ping/pong 作为同步栅栏，确保服务端已处理完上一条消息
        ws.send_json({"type": "ping", "data": {}})
        assert ws.receive_json()["type"] == "pong"

        t_running = tc.get(f"/api/tasks/{task_id}").json()["data"]
        assert t_running["status"] == TaskStatus.RUNNING.value

        # 发送 task_result -> succeeded
        ws.send_json(
            {
                "type": "task_result",
                "data": {"task_id": task_id, "status": "succeeded", "result": {"pong": True}},
            }
        )
        ws.send_json({"type": "ping", "data": {}})
        assert ws.receive_json()["type"] == "pong"

        t_done = tc.get(f"/api/tasks/{task_id}").json()["data"]
        assert t_done["status"] == TaskStatus.SUCCEEDED.value
        assert t_done["result"] == {"pong": True}

        # 重复上报终态任务结果 -> 幂等忽略，状态与结果不被覆盖
        ws.send_json(
            {
                "type": "task_result",
                "data": {"task_id": task_id, "status": "failed", "error": "duplicate"},
            }
        )
        ws.send_json({"type": "ping", "data": {}})
        assert ws.receive_json()["type"] == "pong"

        t_still_done = tc.get(f"/api/tasks/{task_id}").json()["data"]
        assert t_still_done["status"] == TaskStatus.SUCCEEDED.value
        assert t_still_done["result"] == {"pong": True}

    # 确认 DB 中记录完整
    async def _check():
        async with factory() as s:
            task = await TaskService(s).get(task_id)
            assert task.finished_at is not None

    asyncio.run(_check())


def test_ws_task_cancel_and_agent_revoke_disconnect(ws_env):
    tc = ws_env["client"]
    csrf = _login(tc)
    agent_id, secret = _register_agent(tc, csrf)

    resp = tc.post(
        "/api/tasks",
        json={"type": TaskType.SYSTEM_INFO.value, "agent_id": agent_id},
        headers={"X-CSRF-Token": csrf},
    )
    task_id = resp.json()["data"]["task_id"]

    headers = {"X-Agent-Id": agent_id, "Authorization": f"Bearer {secret}"}
    with tc.websocket_connect("/ws/agent", headers=headers) as ws:
        assert ws.receive_json()["type"] == "auth_ok"
        asyncio.run(app.state.scheduler.run_once())
        assert ws.receive_json()["type"] == "task_dispatch"

        # 管理员取消任务 -> 在线 Agent 立即收到 task_cancel
        cancel_resp = tc.post(f"/api/tasks/{task_id}/cancel", headers={"X-CSRF-Token": csrf})
        assert cancel_resp.status_code == 200
        cancel_msg = ws.receive_json()
        assert cancel_msg == {"type": "task_cancel", "data": {"task_id": task_id}}

        # 管理员吊销 Agent -> 在线连接被立即以 4002 关闭
        revoke_resp = tc.post(f"/api/agents/{agent_id}/revoke", headers={"X-CSRF-Token": csrf})
        assert revoke_resp.status_code == 200
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_text()
        assert exc_info.value.code == WS_CLOSE_AGENT_REVOKED


def test_ws_result_without_ack_and_retry(ws_env):
    tc = ws_env["client"]
    csrf = _login(tc)
    agent_id, secret = _register_agent(tc, csrf)

    resp = tc.post(
        "/api/tasks",
        json={"type": TaskType.PING.value, "agent_id": agent_id, "max_attempts": 2},
        headers={"X-CSRF-Token": csrf},
    )
    task_id = resp.json()["data"]["task_id"]

    headers = {"X-Agent-Id": agent_id, "Authorization": f"Bearer {secret}"}
    with tc.websocket_connect("/ws/agent", headers=headers) as ws:
        assert ws.receive_json()["type"] == "auth_ok"
        asyncio.run(app.state.scheduler.run_once())
        assert ws.receive_json()["type"] == "task_dispatch"

        # 模拟 ack 丢失，直接收到失败结果 -> 自动重试回到 queued 且 attempt=1
        ws.send_json(
            {
                "type": "task_result",
                "data": {"task_id": task_id, "status": "failed", "error": "temp err"},
            }
        )
        ws.send_json({"type": "ping", "data": {}})
        assert ws.receive_json()["type"] == "pong"

        t_retry = tc.get(f"/api/tasks/{task_id}").json()["data"]
        assert t_retry["status"] == TaskStatus.QUEUED.value
        assert t_retry["attempt"] == 1
