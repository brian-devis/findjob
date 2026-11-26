"""求职偏好、黑名单过滤、AI 匹配评分、手动/自动投递开关及 WS 回调测试。"""
import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient

from app.core.config import get_settings
from app.core.database import get_db
from app.core.enums import BossJobStatus, TaskType
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.repositories.admin import AdminRepository
from app.services import llm_client


@pytest.mark.asyncio
async def test_preferences_blacklist_ai_score_and_apply_switch(auth, monkeypatch):
    c = auth["client"]
    headers = {"X-CSRF-Token": auth["csrf"]}

    # 1. 默认偏好：manual confirmation（auto_apply_enabled=False）
    r_pref = await c.get("/api/jobs/preferences")
    assert r_pref.status_code == 200
    assert r_pref.json()["data"]["auto_apply_enabled"] is False
    assert r_pref.json()["data"]["auto_apply_min_score"] == 80

    # 2. 更新偏好与屏蔽规则（保持手动确认）
    r_upd = await c.put(
        "/api/jobs/preferences",
        json={
            "keywords": ["Python", "FastAPI"],
            "cities": ["上海"],
            "salary_min": 25,
            "salary_max": 45,
            "exclude_companies": ["外包厂"],
            "exclude_keywords": ["驻场"],
            "auto_apply_enabled": False,
            "auto_apply_min_score": 82,
            "daily_apply_limit": 2,
            "apply_interval_seconds": 30,
        },
        headers=headers,
    )
    assert r_upd.status_code == 200

    # 3. 准备 AI Provider 与激活简历
    await c.post(
        "/api/providers",
        json={
            "name": "ds-pro",
            "base_url": "https://api.example.com/v1",
            "api_format": "openai",
            "model": "deepseek-v4-pro",
            "api_key": "sk-test-1234",
        },
        headers=headers,
    )
    await c.post(
        "/api/resumes",
        json={
            "title": "后端工程师简历",
            "target_role": "Python 后端",
            "raw_content": "5年 FastAPI 与分布式调度开发经验。",
        },
        headers=headers,
    )

    # 4. 导入岗位并校验幂等去重 + 黑名单过滤
    r_imp = await c.post(
        "/api/jobs/import",
        json={
            "items": [
                {
                    "boss_job_id": "boss-101",
                    "title": "高级 Python 工程师",
                    "company": "星辰科技",
                    "city": "上海",
                    "salary": "30-45K",
                    "jd_text": "负责 FastAPI 微服务与 AI 工作流开发。",
                    "tags": ["Python", "FastAPI"],
                },
                {
                    "boss_job_id": "boss-102",
                    "title": "Python 驻场开发",
                    "company": "某某外包厂",
                    "jd_text": "驻场支持",
                },
                {
                    "boss_job_id": "boss-103",
                    "title": "AI 平台后端",
                    "company": "未来智联",
                    "city": "上海",
                    "salary": "32-48K",
                    "jd_text": "构建大模型应用与 Agent 调度平台。",
                },
            ]
        },
        headers=headers,
    )
    assert r_imp.status_code == 200
    imp_data = r_imp.json()["data"]
    assert imp_data["created"] == 3
    assert imp_data["skipped"] == 1

    # 重复导入幂等去重
    r_imp_dup = await c.post(
        "/api/jobs/import",
        json={
            "items": [
                {
                    "boss_job_id": "boss-101",
                    "title": "高级 Python 工程师（更新）",
                    "company": "星辰科技",
                }
            ]
        },
        headers=headers,
    )
    assert r_imp_dup.json()["data"]["updated"] == 1
    assert r_imp_dup.json()["data"]["created"] == 0

    jobs = (await c.get("/api/jobs")).json()["data"]["items"]
    by_eid = {j["boss_job_id"]: j for j in jobs}
    assert by_eid["boss-102"]["status"] == BossJobStatus.SKIPPED.value
    j1_id = by_eid["boss-101"]["id"]
    j3_id = by_eid["boss-103"]["id"]

    # 5. AI 匹配评分与个性化打招呼
    async def fake_score(*, provider, api_key, system_prompt, user_prompt, timeout_seconds=180.0):
        if "未来智联" in user_prompt:
            return {
                "match_score": 88,
                "match_reason": "FastAPI 与 Agent 调度经历高度匹配。",
                "ai_greeting": "您好！我深耕 FastAPI 与 Agent 任务调度系统，过往高并发架构与贵司 AI 平台方向非常契合。",
            }
        return {
            "match_score": 76,
            "match_reason": "基础契合。",
            "ai_greeting": "您好，我对高级 Python 工程师岗位很感兴趣，期待交流！",
        }

    monkeypatch.setattr(llm_client, "complete_json", fake_score)
    r_sc1 = await c.post(f"/api/jobs/{j1_id}/ai-score", json={}, headers=headers)
    assert r_sc1.status_code == 200
    assert r_sc1.json()["data"]["match_score"] == 76

    r_sc3 = await c.post(f"/api/jobs/{j3_id}/ai-score", json={}, headers=headers)
    assert r_sc3.status_code == 200
    assert r_sc3.json()["data"]["match_score"] == 88
    assert r_sc3.json()["data"]["status"] == BossJobStatus.SCORED.value

    # 6. 关闭自动投递时调用 /auto-apply 应被拒绝
    r_auto_off = await c.post("/api/jobs/auto-apply", json={"dry_run": True}, headers=headers)
    assert r_auto_off.status_code == 422

    # 7. 手动开启开关后按分数阈值 (>= 82) 只命中 boss-103，跳过 76 分的 boss-101
    await c.put(
        "/api/jobs/preferences",
        json={"auto_apply_enabled": True, "auto_apply_min_score": 82, "daily_apply_limit": 1},
        headers=headers,
    )
    r_auto_on = await c.post("/api/jobs/auto-apply", json={"dry_run": False}, headers=headers)
    assert r_auto_on.status_code == 200
    auto_data = r_auto_on.json()["data"]
    assert auto_data["dispatched_count"] == 1
    assert auto_data["items"][0]["job_id"] == j3_id

    # 每日投递上限=1 已满（applying 占位），此时手动实操投递 boss-101 应被上限拦截
    r_cap = await c.post(
        f"/api/jobs/{j1_id}/apply", json={"dry_run": False}, headers=headers
    )
    assert r_cap.status_code == 422

    # 预演 dry_run=True 不受每日上限阻塞
    r_dry = await c.post(
        f"/api/jobs/{j1_id}/apply", json={"dry_run": True}, headers=headers
    )
    assert r_dry.status_code == 200


@pytest.fixture
def jobs_ws_env(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs_ws.db"
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


def test_ws_scan_ingests_jobs_and_apply_updates_status(jobs_ws_env):
    tc = jobs_ws_env["client"]
    csrf = tc.post("/api/auth/login", json={"username": "admin", "password": "secret"}).json()[
        "data"
    ]["csrf_token"]
    headers = {"X-CSRF-Token": csrf}

    agent_resp = tc.post("/api/agents", json={"name": "win-agent"}, headers=headers).json()["data"]
    agent_id, secret = agent_resp["agent_id"], agent_resp["secret"]

    # 1. 下发 BOSS_SCAN_JOBS
    scan_task_id = tc.post(
        "/api/jobs/scan",
        json={"agent_id": agent_id, "keywords": ["FastAPI"], "city": "北京", "max_jobs": 5},
        headers=headers,
    ).json()["data"]["task_id"]

    ws_headers = {"X-Agent-Id": agent_id, "Authorization": f"Bearer {secret}"}
    with tc.websocket_connect("/ws/agent", headers=ws_headers) as ws:
        assert ws.receive_json()["type"] == "auth_ok"
        asyncio.run(app.state.scheduler.run_once())
        dispatch = ws.receive_json()
        assert dispatch["type"] == "task_dispatch"
        assert dispatch["data"]["type"] == TaskType.BOSS_SCAN_JOBS.value

        ws.send_json(
            {
                "type": "task_result",
                "data": {
                    "task_id": scan_task_id,
                    "status": "succeeded",
                    "result": {
                        "jobs": [
                            {
                                "boss_job_id": "boss-scan-99",
                                "title": "资深 Python 工程师",
                                "company": "深潜智能",
                                "city": "北京",
                                "salary": "35-50K",
                                "job_url": "https://www.zhipin.com/job_detail/boss-scan-99.html",
                            }
                        ]
                    },
                },
            }
        )
        ws.send_json({"type": "ping", "data": {}})
        assert ws.receive_json()["type"] == "pong"

        jobs = tc.get("/api/jobs").json()["data"]["items"]
        assert len(jobs) == 1
        job_id = jobs[0]["id"]
        assert jobs[0]["status"] == BossJobStatus.DISCOVERED.value

        # 2. 下发 BOSS_APPLY_JOB (dry_run=False) 并回报成功
        apply_task_id = tc.post(
            f"/api/jobs/{job_id}/apply",
            json={"agent_id": agent_id, "greeting": "您好，期待沟通", "dry_run": False},
            headers=headers,
        ).json()["data"]["task"]["task_id"]

        asyncio.run(app.state.scheduler.run_once())
        apply_dispatch = ws.receive_json()
        assert apply_dispatch["data"]["task_id"] == apply_task_id

        ws.send_json(
            {
                "type": "task_result",
                "data": {
                    "task_id": apply_task_id,
                    "status": "succeeded",
                    "result": {"applied": True, "dry_run": False, "needs_human_action": False},
                },
            }
        )
        ws.send_json({"type": "ping", "data": {}})
        assert ws.receive_json()["type"] == "pong"

        updated_job = tc.get("/api/jobs").json()["data"]["items"][0]
        assert updated_job["status"] == BossJobStatus.APPLIED.value
        assert updated_job["applied_at"] is not None


@pytest.mark.asyncio
async def test_batch_score_staggered_auto_apply_stats_and_restore(
    auth, session_factory, monkeypatch
):
    from app.core.exceptions import AppError
    from app.repositories.task import TaskRepository

    c = auth["client"]
    headers = {"X-CSRF-Token": auth["csrf"]}

    await c.post(
        "/api/providers",
        json={
            "name": "ds-pro",
            "base_url": "https://api.example.com/v1",
            "api_format": "openai",
            "model": "deepseek-v4-pro",
            "api_key": "sk-test-1234",
        },
        headers=headers,
    )
    await c.post(
        "/api/resumes",
        json={"title": "主简历", "raw_content": "熟悉 Python / FastAPI / Playwright。"},
        headers=headers,
    )
    await c.put(
        "/api/jobs/preferences",
        json={
            "auto_apply_enabled": True,
            "auto_apply_min_score": 80,
            "daily_apply_limit": 10,
            "apply_interval_seconds": 60,
        },
        headers=headers,
    )

    await c.post(
        "/api/jobs/import",
        json={
            "items": [
                {"boss_job_id": "b-1", "title": "Python 开发 A", "company": "公司 A"},
                {"boss_job_id": "b-2", "title": "Python 开发 B", "company": "公司 B"},
                {"boss_job_id": "b-3", "title": "波动失败岗位", "company": "公司 C"},
            ]
        },
        headers=headers,
    )

    async def fake_batch_score(*, provider, api_key, system_prompt, user_prompt, timeout_seconds=180.0):
        if "波动失败岗位" in user_prompt:
            raise AppError("模拟单条超时", status_code=502, code=1502)
        return {
            "match_score": 90,
            "match_reason": "高度匹配",
            "ai_greeting": "您好，期待进一步沟通！",
        }

    monkeypatch.setattr(llm_client, "complete_json", fake_batch_score)

    # 1. 批量评分：2 成功、1 单条失败容错
    r_batch = await c.post("/api/jobs/ai-score-batch", json={"limit": 10}, headers=headers)
    assert r_batch.status_code == 200
    b_data = r_batch.json()["data"]
    assert b_data["scored"] == 2
    assert b_data["failed"] == 1
    assert len(b_data["errors"]) == 1

    # 2. 忽略其中一条再恢复
    job3_id = next(
        j["id"]
        for j in (await c.get("/api/jobs")).json()["data"]["items"]
        if j["boss_job_id"] == "b-3"
    )
    await c.post(f"/api/jobs/{job3_id}/skip", headers=headers)
    r_res = await c.post(f"/api/jobs/{job3_id}/restore", headers=headers)
    assert r_res.status_code == 200
    assert r_res.json()["data"]["status"] == BossJobStatus.DISCOVERED.value

    # 3. 实操自动批量投递：2 条候选任务应按 apply_interval_seconds=60s 错峰调度
    r_auto = await c.post(
        "/api/jobs/auto-apply", json={"dry_run": False, "max_count": 5}, headers=headers
    )
    assert r_auto.status_code == 200
    items = r_auto.json()["data"]["items"]
    assert len(items) == 2
    assert items[0]["scheduled_at"] is None
    assert items[1]["scheduled_at"] is not None

    async with session_factory() as s:
        t0 = await TaskRepository(s).get_by_task_id(items[0]["task_id"])
        t1 = await TaskRepository(s).get_by_task_id(items[1]["task_id"])
        assert t0 is not None and t0.scheduled_at is None
        assert t1 is not None and t1.scheduled_at is not None

    # 4. 校验 stats 漏斗统计
    list_res = (await c.get("/api/jobs")).json()["data"]
    assert list_res["stats"]["applying"] == 2
    assert list_res["stats"]["discovered"] == 1
