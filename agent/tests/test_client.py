"""Local Agent 客户端协议、幂等、取消、补报与真实后端端到端联调测试。"""
import asyncio
import json
import os
import socket
import sys
from pathlib import Path

import pytest

from agent.client import AgentAuthError, LocalAgentClient, compute_backoff
from agent.config import AgentSettings
from agent.executors import TaskExecutorRegistry
from agent.store import TaskExecutionStore


class FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        return None


def _make_settings(tmp_path: Path, **overrides) -> AgentSettings:
    defaults = {
        "server_ws_url": "ws://127.0.0.1:9999/ws/agent",
        "agent_id": "11111111-1111-1111-1111-111111111111",
        "agent_secret": "super-secret-value-123456",
        "state_db_path": str(tmp_path / "agent.db"),
    }
    defaults.update(overrides)
    return AgentSettings(**defaults)


def test_masked_secret_and_backoff(tmp_path):
    s = _make_settings(tmp_path)
    assert s.masked_secret == "sup****456"
    assert "super-secret-value" not in s.masked_secret

    short = _make_settings(tmp_path, agent_secret="short")
    assert short.masked_secret == "****"

    b1 = compute_backoff(1, base=1.0, cap=60.0)
    b4 = compute_backoff(4, base=1.0, cap=60.0)
    b20 = compute_backoff(20, base=1.0, cap=60.0)
    assert 0.8 <= b1 <= 1.2
    assert 6.4 <= b4 <= 9.6
    assert b20 <= 60.0


@pytest.mark.asyncio
async def test_client_task_idempotency_and_unreported_flush(tmp_path):
    calls = 0

    async def counting_ping(payload):
        nonlocal calls
        calls += 1
        return {"count": calls, "echo": payload}

    registry = TaskExecutorRegistry()
    registry.register("PING", counting_ping)
    store = TaskExecutionStore(tmp_path / "dedup.db")
    client = LocalAgentClient(_make_settings(tmp_path), store=store, registry=registry)
    ws = FakeWS()
    client._active_ws = ws

    dispatch = json.dumps(
        {
            "type": "task_dispatch",
            "data": {
                "task_id": "task-dedup-1",
                "type": "PING",
                "payload": {"v": 1},
                "timeout_seconds": 10,
            },
        }
    )

    # 第一次下发：发 ack、执行 1 次、上报结果并标记 reported=True
    await client.handle_message(ws, dispatch)
    await asyncio.sleep(0.05)
    assert calls == 1
    assert [m["type"] for m in ws.sent] == ["task_ack", "task_result"]
    assert ws.sent[1]["data"]["status"] == "succeeded"
    assert store.get("task-dedup-1").reported is True  # type: ignore[union-attr]

    # 第二次收到相同 task_id：不重复执行，直接重发结果
    ws.sent.clear()
    await client.handle_message(ws, dispatch)
    await asyncio.sleep(0.05)
    assert calls == 1
    assert [m["type"] for m in ws.sent] == ["task_result"]

    # 模拟断线期间落盘未上报结果，重连后 _flush_unreported 自动补报
    store.save_result(
        task_id="task-offline-2",
        status="succeeded",
        result={"offline": True},
        reported=False,
    )
    ws.sent.clear()
    await client._flush_unreported(ws)
    assert len(ws.sent) == 1
    assert ws.sent[0]["type"] == "task_result"
    assert ws.sent[0]["data"]["task_id"] == "task-offline-2"
    assert store.get("task-offline-2").reported is True  # type: ignore[union-attr]

    await client.close()
    store.close()


@pytest.mark.asyncio
async def test_client_task_cancel_stops_running_task(tmp_path):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def long_job(payload):
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {"done": True}

    registry = TaskExecutorRegistry()
    registry.register("PING", long_job)
    client = LocalAgentClient(_make_settings(tmp_path), registry=registry)
    ws = FakeWS()
    client._active_ws = ws

    await client.handle_message(
        ws,
        json.dumps(
            {
                "type": "task_dispatch",
                "data": {"task_id": "t-cancel", "type": "PING", "payload": {}, "timeout_seconds": 30},
            }
        ),
    )
    await asyncio.wait_for(started.wait(), timeout=1.0)

    await client.handle_message(
        ws, json.dumps({"type": "task_cancel", "data": {"task_id": "t-cancel"}})
    )
    await asyncio.wait_for(cancelled.wait(), timeout=1.0)
    await asyncio.sleep(0.02)
    assert client.store.get("t-cancel") is None
    await client.close()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.asyncio
async def test_client_handles_malformed_data_and_invalid_timeout(tmp_path):
    client = LocalAgentClient(_make_settings(tmp_path))
    ws = FakeWS()
    client._active_ws = ws

    # 非 dict 的 data 字段应安全忽略而不抛出 AttributeError
    await client.handle_message(ws, json.dumps({"type": "task_dispatch", "data": ["bad"]}))
    await client.handle_message(ws, json.dumps({"type": "task_cancel", "data": "bad"}))

    # 非法 timeout_seconds 应安全回退默认值并正常执行
    await client.handle_message(
        ws,
        json.dumps(
            {
                "type": "task_dispatch",
                "data": {
                    "task_id": "t-bad-timeout",
                    "type": "PING",
                    "payload": {},
                    "timeout_seconds": "abc",
                },
            }
        ),
    )
    await asyncio.sleep(0.05)
    assert any(m["type"] == "task_result" and m["data"]["task_id"] == "t-bad-timeout" for m in ws.sent)
    await client.close()


@pytest.mark.asyncio
async def test_client_retries_failed_task_and_handles_handshake_timeout(tmp_path, monkeypatch):
    # 1. 本地记录为 failed 时，收到同 task_id 下发允许重新执行并覆盖为 succeeded
    store = TaskExecutionStore(tmp_path / "retry_failed.db")
    store.save_result(
        task_id="t-retry-failed",
        status="failed",
        error="previous timeout",
        reported=True,
    )
    client = LocalAgentClient(_make_settings(tmp_path), store=store)
    ws = FakeWS()
    client._active_ws = ws

    await client.handle_message(
        ws,
        json.dumps(
            {
                "type": "task_dispatch",
                "data": {"task_id": "t-retry-failed", "type": "PING", "payload": {"r": 2}},
            }
        ),
    )
    await asyncio.sleep(0.05)
    assert [m["type"] for m in ws.sent] == ["task_ack", "task_result"]
    assert ws.sent[1]["data"]["status"] == "succeeded"
    assert store.get("t-retry-failed").status == "succeeded"  # type: ignore[union-attr]
    await client.close()
    store.close()

    # 2. 首次握手超时应触发重连逻辑并在 stop() 后安全退出，不崩溃
    class HangingWS:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def recv(self):
            await asyncio.sleep(10)

        async def close(self, code: int = 1000, reason: str = "") -> None:
            return None

    attempts = 0

    def fake_connect(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts >= 2:
            timeout_client.stop()
        return HangingWS()

    import websockets

    monkeypatch.setattr(websockets, "connect", fake_connect)
    timeout_client = LocalAgentClient(
        _make_settings(
            tmp_path,
            recv_timeout_seconds=0.05,
            reconnect_base_seconds=0.01,
            reconnect_max_seconds=0.02,
            state_db_path=str(tmp_path / "timeout_agent.db"),
        )
    )
    await asyncio.wait_for(timeout_client.run_forever(), timeout=2.0)
    assert attempts >= 2
    await timeout_client.close()


@pytest.mark.asyncio
async def test_end_to_end_with_real_backend(tmp_path):
    """端到端联调：启动真实 FastAPI 后端，验证 LocalAgentClient 鉴权、任务执行与结果回传。"""
    uvicorn = pytest.importorskip("uvicorn")
    pytest.importorskip("fastapi")
    pytest.importorskip("sqlalchemy")
    backend_dir = Path(__file__).resolve().parents[2] / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    os.environ.setdefault("JWT_SECRET", "aijob-e2e-secret-0123456789abcdef0123456789abcdef")

    from app.core.enums import TaskStatus, TaskType
    from app.main import app as backend_app
    from app.models import Base
    from app.services.agent_service import AgentService
    from app.services.task_service import TaskService
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    db_path = tmp_path / "backend_e2e.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session:
        agent_obj, secret = await AgentService(session).register("e2e-win-agent")
        t1 = await TaskService(session).create(
            type_=TaskType.PING,
            agent_id=agent_obj.agent_id,
            payload={"hello": "world"},
            priority=10,
            max_attempts=1,
            timeout_seconds=30,
        )
        t2 = await TaskService(session).create(
            type_=TaskType.SYSTEM_INFO,
            agent_id=agent_obj.agent_id,
            payload={},
            priority=5,
            max_attempts=1,
            timeout_seconds=30,
        )
        await session.commit()

    backend_app.state.session_factory = factory
    port = _find_free_port()
    config = uvicorn.Config(backend_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # 等待后端监听就绪
    for _ in range(50):
        if server.started:
            break
        await asyncio.sleep(0.05)
    assert server.started

    ws_url = f"ws://127.0.0.1:{port}/ws/agent"

    try:
        # 1. 错误密钥应触发 AgentAuthError 且不无限重试
        bad_client = LocalAgentClient(
            _make_settings(
                tmp_path,
                server_ws_url=ws_url,
                agent_id=agent_obj.agent_id,
                agent_secret="wrong-secret-value",
                state_db_path=str(tmp_path / "bad_agent.db"),
            )
        )
        with pytest.raises(AgentAuthError):
            await asyncio.wait_for(bad_client.run_forever(), timeout=3.0)
        await bad_client.close()

        # 2. 正确密钥连接并自动完成 PING 与 SYSTEM_INFO 两个任务
        good_client = LocalAgentClient(
            _make_settings(
                tmp_path,
                server_ws_url=ws_url,
                agent_id=agent_obj.agent_id,
                agent_secret=secret,
                state_db_path=str(tmp_path / "good_agent.db"),
                heartbeat_interval_seconds=5.0,
                recv_timeout_seconds=15.0,
            )
        )
        agent_task = asyncio.create_task(good_client.run_forever())

        try:
            # 轮询等待后端两个任务均进入 succeeded
            for _ in range(80):
                async with factory() as session:
                    svc = TaskService(session)
                    r1 = await svc.get(t1.task_id)
                    r2 = await svc.get(t2.task_id)
                    if (
                        r1.status == TaskStatus.SUCCEEDED.value
                        and r2.status == TaskStatus.SUCCEEDED.value
                    ):
                        break
                await asyncio.sleep(0.05)

            assert r1.status == TaskStatus.SUCCEEDED.value
            assert r1.result is not None and r1.result["pong"] is True
            assert r1.result["echo"] == {"hello": "world"}

            assert r2.status == TaskStatus.SUCCEEDED.value
            assert r2.result is not None and r2.result["hostname"]
            assert r2.result["cpu_count"] >= 1

            # 校验 Agent 本地持久化已标记 reported=True
            rec1 = good_client.store.get(t1.task_id)
            rec2 = good_client.store.get(t2.task_id)
            assert rec1 is not None and rec1.reported is True
            assert rec2 is not None and rec2.reported is True
        finally:
            await good_client.close()
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass
    finally:
        server.should_exit = True
        await server_task
        if hasattr(backend_app.state, "session_factory"):
            delattr(backend_app.state, "session_factory")
        await engine.dispose()
