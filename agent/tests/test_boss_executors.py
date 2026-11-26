"""BOSS 浏览器状态识别、优势提取与执行器单元测试。"""
from typing import Any

import pytest

from agent.boss_executors import (
    MAX_ADVANTAGE_LEN,
    extract_boss_advantage,
    register_boss_executors,
)
from agent.browser import detect_boss_page_state
from agent.executors import TaskExecutorRegistry


class FakeBossBrowser:
    def __init__(
        self,
        *,
        login_result: dict[str, Any] | None = None,
        sync_result: dict[str, Any] | None = None,
    ) -> None:
        self.login_result = login_result or {
            "logged_in": True,
            "needs_human_action": False,
            "reason": "ok",
            "message": "BOSS 直聘登录状态有效",
            "current_url": "https://www.zhipin.com/web/geek/resume",
        }
        self.sync_result = sync_result
        self.sync_calls: list[dict[str, Any]] = []
        self.closed = False

    async def check_boss_login(self) -> dict[str, Any]:
        return dict(self.login_result)

    async def sync_boss_resume(self, **kwargs: Any) -> dict[str, Any]:
        self.sync_calls.append(kwargs)
        if self.sync_result is not None:
            return dict(self.sync_result)
        dry_run = bool(kwargs["dry_run"])
        return {
            "synced": not dry_run,
            "dry_run": dry_run,
            "logged_in": True,
            "needs_human_action": False,
            "reason": "dry_run_preview" if dry_run else "ok",
            "preview": {
                "title": kwargs["title"],
                "advantage_text": kwargs["advantage_text"],
                "skills": kwargs["skills"],
            },
        }

    async def scan_boss_jobs(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs["dry_run"]:
            return {"jobs": [], "dry_run": True, "logged_in": True, "needs_human_action": False}
        return {
            "jobs": [
                {
                    "boss_job_id": "boss-job-1",
                    "title": f"{kwargs['keywords'][0]} 开发",
                    "company": "星辰科技",
                    "city": kwargs.get("city"),
                }
            ][: kwargs["max_jobs"]],
            "dry_run": False,
            "logged_in": True,
            "needs_human_action": False,
        }

    async def apply_boss_job(self, **kwargs: Any) -> dict[str, Any]:
        if self.sync_result is not None:
            return dict(self.sync_result)
        dry_run = bool(kwargs["dry_run"])
        return {
            "applied": not dry_run,
            "dry_run": dry_run,
            "logged_in": True,
            "needs_human_action": False,
            "reason": "dry_run_preview" if dry_run else "ok",
        }

    async def close(self) -> None:
        self.closed = True


def test_detect_boss_page_state():
    # 1. 已登录个人简历页
    ok_state = detect_boss_page_state(
        "https://www.zhipin.com/web/geek/resume", "在线简历 编辑 个人优势"
    )
    assert ok_state["logged_in"] is True
    assert ok_state["needs_human_action"] is False
    assert ok_state["reason"] == "ok"

    # 2. 登录页（扫码/短信登录）
    login_state = detect_boss_page_state(
        "https://www.zhipin.com/web/user/?ka=header-login", "APP扫码登录 验证码登录"
    )
    assert login_state["logged_in"] is False
    assert login_state["needs_human_action"] is True
    assert login_state["reason"] == "login_required"

    # 3. 风控验证码页：绝不尝试绕过，必须返回 verification_required
    verify_state = detect_boss_page_state(
        "https://www.zhipin.com/web/user/safe/verify-slider", "请拖动滑块完成安全验证"
    )
    assert verify_state["logged_in"] is False
    assert verify_state["needs_human_action"] is True
    assert verify_state["reason"] == "verification_required"

    # 4. 未知页面保守返回 needs_human_action
    unknown_state = detect_boss_page_state("https://www.zhipin.com/", "首页")
    assert unknown_state["logged_in"] is False
    assert unknown_state["needs_human_action"] is True


def test_extract_boss_advantage():
    structured = {"summary": "  7年 Python 架构与高并发微服务经验  ", "skills": ["Python", "FastAPI"]}
    assert extract_boss_advantage("# 原文\n内容", structured) == "7年 Python 架构与高并发微服务经验"

    # 回退解析 Markdown 并限制最大长度
    long_md = "# 个人优势\n- 主导 FastAPI 网关\n" + ("核心性能调优经验 " * 120)
    fallback = extract_boss_advantage(long_md, {})
    assert fallback.startswith("个人优势\n主导 FastAPI 网关")
    assert len(fallback) <= MAX_ADVANTAGE_LEN


@pytest.mark.asyncio
async def test_boss_executors_check_login_and_sync_modes():
    browser = FakeBossBrowser()
    registry = TaskExecutorRegistry()
    register_boss_executors(registry, browser)

    # 1. check_login
    chk = await registry.execute("BOSS_CHECK_LOGIN", {})
    assert chk["logged_in"] is True
    assert chk["needs_human_action"] is False
    assert "timestamp" in chk

    # 2. dry_run=True（默认预演）
    dry = await registry.execute(
        "BOSS_SYNC_RESUME",
        {
            "resume_id": 7,
            "title": "后端开发 v2",
            "target_role": "Python 后端",
            "raw_content": "# 个人优势\n熟悉 FastAPI",
            "structured_json": {"summary": "5年 Python 后端经验", "skills": ["Python", "FastAPI"]},
        },
    )
    assert dry["resume_id"] == 7
    assert dry["dry_run"] is True
    assert dry["synced"] is False
    assert browser.sync_calls[-1]["dry_run"] is True
    assert browser.sync_calls[-1]["advantage_text"] == "5年 Python 后端经验"

    # 3. dry_run=False 实操同步
    live = await registry.execute(
        "BOSS_SYNC_RESUME",
        {
            "resume_id": 7,
            "title": "后端开发 v2",
            "raw_content": "# 个人优势\n熟悉 FastAPI",
            "structured_json": {"summary": "5年 Python 后端经验"},
            "dry_run": False,
        },
    )
    assert live["dry_run"] is False
    assert live["synced"] is True
    assert live["needs_human_action"] is False

    # 4. 登录或验证拦截时短路透传 needs_human_action=True
    human_browser = FakeBossBrowser(
        sync_result={
            "synced": False,
            "dry_run": False,
            "logged_in": False,
            "needs_human_action": True,
            "reason": "login_required",
            "message": "请扫码登录",
        }
    )
    human_reg = TaskExecutorRegistry()
    register_boss_executors(human_reg, human_browser)
    blocked = await human_reg.execute(
        "BOSS_SYNC_RESUME",
        {"resume_id": 9, "raw_content": "熟悉 Python", "dry_run": False},
    )
    assert blocked["synced"] is False
    assert blocked["needs_human_action"] is True
    assert blocked["reason"] == "login_required"

    # 5. 缺少 raw_content 抛 ValueError
    with pytest.raises(ValueError):
        await registry.execute("BOSS_SYNC_RESUME", {"resume_id": 1, "raw_content": "   "})


@pytest.mark.asyncio
async def test_boss_scan_and_apply_executors():
    browser = FakeBossBrowser()
    registry = TaskExecutorRegistry()
    register_boss_executors(registry, browser)

    # 1. BOSS_SCAN_JOBS 正常扫描
    scan_res = await registry.execute(
        "BOSS_SCAN_JOBS",
        {"keywords": ["Python", "FastAPI"], "city": "上海", "max_jobs": 5},
    )
    assert len(scan_res["jobs"]) == 1
    assert scan_res["jobs"][0]["boss_job_id"] == "boss-job-1"
    assert "timestamp" in scan_res

    with pytest.raises(ValueError):
        await registry.execute("BOSS_SCAN_JOBS", {"keywords": []})

    # 2. BOSS_APPLY_JOB dry_run=True 与 dry_run=False
    dry_apply = await registry.execute(
        "BOSS_APPLY_JOB",
        {
            "job_id": 12,
            "boss_job_id": "boss-job-1",
            "title": "Python 开发",
            "company": "星辰科技",
            "greeting": "您好，期待交流",
        },
    )
    assert dry_apply["dry_run"] is True
    assert dry_apply["applied"] is False
    assert dry_apply["job_id"] == 12

    live_apply = await registry.execute(
        "BOSS_APPLY_JOB",
        {
            "job_id": 12,
            "boss_job_id": "boss-job-1",
            "title": "Python 开发",
            "company": "星辰科技",
            "greeting": "您好，期待交流",
            "dry_run": False,
        },
    )
    assert live_apply["dry_run"] is False
    assert live_apply["applied"] is True

    # 3. 遇安全验证拦截直接透传 needs_human_action=True
    verify_browser = FakeBossBrowser(
        sync_result={
            "applied": False,
            "dry_run": False,
            "logged_in": False,
            "needs_human_action": True,
            "reason": "verification_required",
            "message": "请手动完成滑块验证",
        }
    )
    verify_reg = TaskExecutorRegistry()
    register_boss_executors(verify_reg, verify_browser)
    blocked = await verify_reg.execute(
        "BOSS_APPLY_JOB",
        {
            "job_id": 15,
            "boss_job_id": "boss-job-2",
            "title": "架构师",
            "company": "某某",
            "greeting": "您好",
            "dry_run": False,
        },
    )
    assert blocked["applied"] is False
    assert blocked["needs_human_action"] is True
    assert blocked["reason"] == "verification_required"

    with pytest.raises(ValueError):
        await registry.execute("BOSS_APPLY_JOB", {"boss_job_id": "x", "title": "t"})
