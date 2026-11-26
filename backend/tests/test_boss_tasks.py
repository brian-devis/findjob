"""BOSS 登录检测与简历同步任务接口及 WS 回调测试。"""
import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient

from app.core.config import get_settings
from app.core.database import get_db
from app.core.enums import TaskStatus, TaskType
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.repositories.admin import AdminRepository
from app.repositories.resume import ResumeRepository


@pytest.mark.asyncio
async def test_check_boss_login_and_sync_boss_endpoints(auth):
    c = auth["client"]
    headers = {"X-CSRF-Token": auth["csrf"]}

    # 注册两个 Agent，其中一个稍后吊销
    r_a1 = await c.post("/api/agents", json={"name": "win-boss-01"}, headers=headers)
    assert r_a1.status_code == 200
    a1_id = r_a1.json()["data"]["agent_id"]

    r_a2 = await c.post("/api/agents", json={"name": "win-revoked"}, headers=headers)
    a2_id = r_a2.json()["data"]["agent_id"]
    await c.post(f"/api/agents/{a2_id}/revoke", headers=headers)

    # 1. check-boss-login：正常创建任务并记审计日志
    r_chk = await c.post(f"/api/agents/{a1_id}/check-boss-login", headers=headers)
    assert r_chk.status_code == 200
    t_chk = r_chk.json()["data"]
    assert t_chk["type"] == TaskType.BOSS_CHECK_LOGIN.value
    assert t_chk["agent_id"] == a1_id
    assert t_chk["status"] == TaskStatus.QUEUED.value

    # 已吊销 Agent 拒绝创建
    r_chk_revoked = await c.post(f"/api/agents/{a2_id}/check-boss-login", headers=headers)
    assert r_chk_revoked.status_code == 422

    # 2. 创建简历并下发 sync-boss（默认 dry_run=True）
    r_res = await c.post(
        "/api/resumes",
        json={
            "title": "BOSS 同步测试简历",
            "target_role": "Python 后端开发",
            "raw_content": "# 个人优势\n熟悉 FastAPI 与分布式任务调度",
            "structured_json": {"summary": "熟悉 FastAPI 与分布式任务调度", "skills": ["Python", "FastAPI"]},
        },
        headers=headers,
    )
    assert r_res.status_code == 200
    resume_id = r_res.json()["data"]["id"]

    r_sync_dry = await c.post(
        f"/api/resumes/{resume_id}/sync-boss",
        json={"agent_id": a1_id},
        headers=headers,
    )
    assert r_sync_dry.status_code == 200
    t_dry = r_sync_dry.json()["data"]
    assert t_dry["type"] == TaskType.BOSS_SYNC_RESUME.value
    assert t_dry["payload"]["resume_id"] == resume_id
    assert t_dry["payload"]["dry_run"] is True
    assert t_dry["payload"]["structured_json"]["skills"] == ["Python", "FastAPI"]

    # 指定已吊销 Agent 应拒绝
    r_sync_revoked = await c.post(
        f"/api/resumes/{resume_id}/sync-boss",
        json={"agent_id": a2_id, "dry_run": False},
        headers=headers,
    )
    assert r_sync_revoked.status_code == 422

    # 审计日志校验
    r_audit1 = await c.get("/api/audit-logs?action=agent.check_boss_login")
    assert r_audit1.json()["data"]["total"] == 1
    r_audit2 = await c.get("/api/audit-logs?action=resume.sync_boss")
    assert r_audit2.json()["data"]["total"] == 1


@pytest.fixture
def boss_ws_env(tmp_path, monkeypatch):
    db_path = tmp_path / "boss_ws.db"
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


def test_ws_boss_sync_updates_synced_at_only_when_live_synced(boss_ws_env):
    tc = boss_ws_env["client"]
    factory = boss_ws_env["factory"]
    csrf = tc.post("/api/auth/login", json={"username": "admin", "password": "secret"}).json()[
        "data"
    ]["csrf_token"]
    headers = {"X-CSRF-Token": csrf}

    agent_resp = tc.post("/api/agents", json={"name": "win-agent"}, headers=headers).json()["data"]
    agent_id, secret = agent_resp["agent_id"], agent_resp["secret"]

    resume_id = tc.post(
        "/api/resumes",
        json={"title": "同步状态校验", "raw_content": "Python / Playwright 经验"},
        headers=headers,
    ).json()["data"]["id"]

    t_dry = tc.post(
        f"/api/resumes/{resume_id}/sync-boss",
        json={"agent_id": agent_id, "dry_run": True},
        headers=headers,
    ).json()["data"]["task_id"]

    t_human = tc.post(
        f"/api/resumes/{resume_id}/sync-boss",
        json={"agent_id": agent_id, "dry_run": False},
        headers=headers,
    ).json()["data"]["task_id"]

    t_live = tc.post(
        f"/api/resumes/{resume_id}/sync-boss",
        json={"agent_id": agent_id, "dry_run": False},
        headers=headers,
    ).json()["data"]["task_id"]

    ws_headers = {"X-Agent-Id": agent_id, "Authorization": f"Bearer {secret}"}
    with tc.websocket_connect("/ws/agent", headers=ws_headers) as ws:
        assert ws.receive_json()["type"] == "auth_ok"
        asyncio.run(app.state.scheduler.run_once())
        dispatched = [ws.receive_json()["data"]["task_id"] for _ in range(3)]
        assert set(dispatched) == {t_dry, t_human, t_live}

        # 1. dry_run=True 回报不应更新 synced_to_boss_at
        ws.send_json(
            {
                "type": "task_result",
                "data": {
                    "task_id": t_dry,
                    "status": "succeeded",
                    "result": {"synced": False, "dry_run": True, "needs_human_action": False},
                },
            }
        )
        # 2. 需要人工处理时不应更新 synced_to_boss_at
        ws.send_json(
            {
                "type": "task_result",
                "data": {
                    "task_id": t_human,
                    "status": "succeeded",
                    "result": {"synced": False, "dry_run": False, "needs_human_action": True},
                },
            }
        )
        ws.send_json({"type": "ping", "data": {}})
        assert ws.receive_json()["type"] == "pong"

        r_before = tc.get(f"/api/resumes/{resume_id}").json()["data"]
        assert r_before["synced_to_boss_at"] is None

        # 3. 非预演且 synced=True 且无需人工处理时应写入 synced_to_boss_at
        ws.send_json(
            {
                "type": "task_result",
                "data": {
                    "task_id": t_live,
                    "status": "succeeded",
                    "result": {"synced": True, "dry_run": False, "needs_human_action": False},
                },
            }
        )
        ws.send_json({"type": "ping", "data": {}})
        assert ws.receive_json()["type"] == "pong"

    async def _verify():
        async with factory() as s:
            r = await ResumeRepository(s).get_by_id(resume_id)
            assert r is not None
            assert r.synced_to_boss_at is not None

    asyncio.run(_verify())
