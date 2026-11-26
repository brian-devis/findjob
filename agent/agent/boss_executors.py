"""BOSS 直聘相关本地任务执行器（登录检测与简历同步）。"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from agent.browser import BossBrowserAdapter
from agent.executors import TaskExecutorRegistry

MAX_ADVANTAGE_LEN = 1000


def extract_boss_advantage(
    raw_content: str,
    structured_json: dict[str, Any] | None = None,
) -> str:
    """提取适合填写到 BOSS 直聘「个人优势」栏的纯文本内容（≤ 1000 字符）。"""
    if isinstance(structured_json, dict):
        summary = structured_json.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()[:MAX_ADVANTAGE_LEN]

    lines: list[str] = []
    for raw_line in (raw_content or "").splitlines():
        cleaned = re.sub(r"^#{1,6}\s*", "", raw_line).strip()
        cleaned = re.sub(r"^[-*+]\s+", "", cleaned).strip()
        if cleaned:
            lines.append(cleaned)
    text = "\n".join(lines).strip()
    return text[:MAX_ADVANTAGE_LEN]


def extract_skills(structured_json: dict[str, Any] | None = None) -> list[str]:
    if not isinstance(structured_json, dict):
        return []
    raw_skills = structured_json.get("skills")
    if not isinstance(raw_skills, list):
        return []
    return [str(item).strip() for item in raw_skills if str(item).strip()][:20]


def register_boss_executors(
    registry: TaskExecutorRegistry,
    browser: BossBrowserAdapter,
) -> None:
    """向任务执行器注册中心注册 BOSS 直聘任务处理器。"""

    async def execute_boss_check_login(payload: dict[str, Any]) -> dict[str, Any]:
        result = await browser.check_boss_login()
        result["timestamp"] = datetime.now(UTC).isoformat()
        return result

    async def execute_boss_sync_resume(payload: dict[str, Any]) -> dict[str, Any]:
        raw_content = payload.get("raw_content")
        if not isinstance(raw_content, str) or not raw_content.strip():
            raise ValueError("BOSS_SYNC_RESUME payload 缺少非空 raw_content")

        structured = payload.get("structured_json")
        structured_json = structured if isinstance(structured, dict) else {}
        title = str(payload.get("title") or "我的简历").strip()
        raw_role = payload.get("target_role")
        target_role = str(raw_role).strip() if isinstance(raw_role, str) and raw_role.strip() else None
        dry_run = bool(payload.get("dry_run", True))

        advantage_text = extract_boss_advantage(raw_content, structured_json)
        if not advantage_text:
            raise ValueError("无法从简历正文提取个人优势文本")
        skills = extract_skills(structured_json)

        res = await browser.sync_boss_resume(
            title=title,
            target_role=target_role,
            advantage_text=advantage_text,
            skills=skills,
            raw_content=raw_content,
            structured_json=structured_json,
            dry_run=dry_run,
        )
        res.setdefault("dry_run", dry_run)
        if "resume_id" in payload:
            res["resume_id"] = payload["resume_id"]
        res["timestamp"] = datetime.now(UTC).isoformat()
        return res

    registry.register("BOSS_CHECK_LOGIN", execute_boss_check_login)
    registry.register("BOSS_SYNC_RESUME", execute_boss_sync_resume)

    async def execute_boss_scan_jobs(payload: dict[str, Any]) -> dict[str, Any]:
        raw_keywords = payload.get("keywords")
        if not isinstance(raw_keywords, list):
            raise TypeError("BOSS_SCAN_JOBS payload 缺少 keywords 列表")
        keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
        if not keywords:
            raise ValueError("BOSS_SCAN_JOBS keywords 不能为空")

        raw_city = payload.get("city")
        city = str(raw_city).strip() if isinstance(raw_city, str) and raw_city.strip() else None
        try:
            max_jobs = max(1, min(int(payload.get("max_jobs", 20)), 50))
        except (TypeError, ValueError):
            max_jobs = 20
        dry_run = bool(payload.get("dry_run", False))

        res = await browser.scan_boss_jobs(
            keywords=keywords,
            city=city,
            max_jobs=max_jobs,
            dry_run=dry_run,
        )
        res.setdefault("dry_run", dry_run)
        res["timestamp"] = datetime.now(UTC).isoformat()
        return res

    async def execute_boss_apply_job(payload: dict[str, Any]) -> dict[str, Any]:
        boss_job_id = str(payload.get("boss_job_id") or "").strip()
        title = str(payload.get("title") or "").strip()
        company = str(payload.get("company") or "").strip()
        greeting = str(payload.get("greeting") or "").strip()
        if not boss_job_id or not title or not greeting:
            raise ValueError("BOSS_APPLY_JOB payload 缺少 boss_job_id / title / greeting")

        raw_url = payload.get("job_url")
        job_url = str(raw_url).strip() if isinstance(raw_url, str) and raw_url.strip() else None
        dry_run = bool(payload.get("dry_run", True))

        res = await browser.apply_boss_job(
            boss_job_id=boss_job_id,
            title=title,
            company=company,
            job_url=job_url,
            greeting=greeting,
            dry_run=dry_run,
        )
        res.setdefault("dry_run", dry_run)
        if "job_id" in payload:
            res["job_id"] = payload["job_id"]
        res["boss_job_id"] = boss_job_id
        res["timestamp"] = datetime.now(UTC).isoformat()
        return res

    registry.register("BOSS_SCAN_JOBS", execute_boss_scan_jobs)
    registry.register("BOSS_APPLY_JOB", execute_boss_apply_job)
