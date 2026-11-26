"""求职偏好、BOSS 岗位扫描/导入、AI 匹配评分与自动/手动投递服务。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AgentStatus, BossJobStatus, TaskType
from app.core.exceptions import AppError, NotFoundError, ValidationError
from app.core.time import utcnow
from app.models.ai_provider import AIProvider
from app.models.job import BossJob, JobPreference
from app.models.task import Task
from app.repositories.job import BossJobRepository, JobPreferenceRepository
from app.repositories.provider import AIProviderRepository
from app.repositories.resume import ResumeRepository
from app.services import llm_client
from app.services.agent_service import AgentService
from app.services.provider_service import ProviderService
from app.services.task_service import TaskService

_JOB_SCORE_SYSTEM_PROMPT = """你是一位资深技术猎头与求职顾问，负责评估候选人简历与 BOSS 直聘岗位的匹配度，并撰写得体、有针对性的首句打招呼文案。
请严格输出一个 JSON 对象，不要输出任何多余解释文字，格式如下：
{
  "match_score": 0-100 的整数评分,
  "match_reason": "2-3 句匹配分析（指出契合点与潜在差距）",
  "ai_greeting": "60-140 字中文开场白（直接面向招聘方/HR，自然提及自身与岗位最贴合的 1-2 个项目亮点，真诚专业，不浮夸）"
}"""


def _match_blacklist(
    *,
    title: str,
    company: str,
    jd_text: str,
    pref: JobPreference,
) -> str | None:
    company_lower = company.lower()
    for blocked in pref.exclude_companies or []:
        b = str(blocked).strip()
        if b and b.lower() in company_lower:
            return f"命中屏蔽公司规则：{b}"

    haystack = f"{title}\n{jd_text}".lower()
    for kw in pref.exclude_keywords or []:
        k = str(kw).strip()
        if k and k.lower() in haystack:
            return f"命中屏蔽关键词：{k}"
    return None


class JobService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._pref_repo = JobPreferenceRepository(session)
        self._job_repo = BossJobRepository(session)
        self._resume_repo = ResumeRepository(session)
        self._provider_repo = AIProviderRepository(session)

    # ---- 偏好设置 ----
    async def get_preference(self) -> JobPreference:
        pref = await self._pref_repo.get_or_create_default()
        await self._session.flush()
        return pref

    async def update_preference(self, **fields: Any) -> JobPreference:
        pref = await self._pref_repo.get_or_create_default()
        if fields.get("provider_id") is not None:
            provider = await self._provider_repo.get_by_id(fields["provider_id"])
            if provider is None:
                raise NotFoundError("指定的 AI Provider 不存在")
        for key, value in fields.items():
            if hasattr(pref, key):
                setattr(pref, key, value)
        await self._session.flush()
        return pref

    # ---- 岗位查询与导入 ----
    async def get_job(self, job_id: int) -> BossJob:
        job = await self._job_repo.get_by_id(job_id)
        if job is None:
            raise NotFoundError("岗位不存在")
        return job

    async def list_jobs(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
        min_score: int | None = None,
    ) -> dict[str, Any]:
        pref = await self.get_preference()
        items = await self._job_repo.list(
            offset=offset, limit=limit, status=status, min_score=min_score
        )
        total = await self._job_repo.count(status=status, min_score=min_score)
        applied_today = await self._job_repo.count_applied_today()
        raw_counts = await self._job_repo.status_counts()
        high_score_ready = await self._job_repo.count_high_score_ready(
            min_score=pref.auto_apply_min_score
        )
        stats = {
            "discovered": raw_counts.get(BossJobStatus.DISCOVERED.value, 0),
            "scored": raw_counts.get(BossJobStatus.SCORED.value, 0),
            "applying": raw_counts.get(BossJobStatus.APPLYING.value, 0),
            "applied": raw_counts.get(BossJobStatus.APPLIED.value, 0),
            "failed": raw_counts.get(BossJobStatus.FAILED.value, 0),
            "skipped": raw_counts.get(BossJobStatus.SKIPPED.value, 0),
            "high_score_ready": high_score_ready,
        }
        return {
            "items": items,
            "total": total,
            "applied_today": applied_today,
            "daily_apply_limit": pref.daily_apply_limit,
            "auto_apply_enabled": pref.auto_apply_enabled,
            "auto_apply_min_score": pref.auto_apply_min_score,
            "stats": stats,
        }

    async def ingest_jobs(self, raw_items: list[dict[str, Any]]) -> dict[str, Any]:
        pref = await self.get_preference()
        created = 0
        updated = 0
        skipped = 0
        saved: list[BossJob] = []

        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            boss_job_id = str(raw.get("boss_job_id") or "").strip()[:128]
            title = str(raw.get("title") or "").strip()[:255]
            company = str(raw.get("company") or "").strip()[:255]
            if not boss_job_id or not title or not company:
                continue

            city = str(raw.get("city") or "").strip()[:64] or None
            salary = str(raw.get("salary") or "").strip()[:64] or None
            experience = str(raw.get("experience") or "").strip()[:64] or None
            education = str(raw.get("education") or "").strip()[:64] or None
            recruiter = str(raw.get("recruiter") or "").strip()[:128] or None
            job_url = str(raw.get("job_url") or "").strip()[:512] or None
            jd_text = str(raw.get("jd_text") or "").strip()
            tags = [str(t).strip() for t in (raw.get("tags") or []) if str(t).strip()][:20]

            blacklist_reason = _match_blacklist(
                title=title, company=company, jd_text=jd_text, pref=pref
            )
            existing = await self._job_repo.get_by_boss_job_id(boss_job_id)
            if existing is not None:
                existing.title = title
                existing.company = company
                if city:
                    existing.city = city
                if salary:
                    existing.salary = salary
                if experience:
                    existing.experience = experience
                if education:
                    existing.education = education
                if recruiter:
                    existing.recruiter = recruiter
                if job_url:
                    existing.job_url = job_url
                if jd_text:
                    existing.jd_text = jd_text
                if tags:
                    existing.tags = tags
                if blacklist_reason and existing.status == BossJobStatus.DISCOVERED.value:
                    existing.status = BossJobStatus.SKIPPED.value
                    existing.last_error = blacklist_reason
                    skipped += 1
                updated += 1
                saved.append(existing)
                continue

            status = (
                BossJobStatus.SKIPPED.value
                if blacklist_reason
                else BossJobStatus.DISCOVERED.value
            )
            if blacklist_reason:
                skipped += 1
            job = BossJob(
                boss_job_id=boss_job_id,
                title=title,
                company=company,
                city=city,
                salary=salary,
                experience=experience,
                education=education,
                recruiter=recruiter,
                job_url=job_url,
                jd_text=jd_text,
                tags=tags,
                status=status,
                last_error=blacklist_reason,
            )
            self._session.add(job)
            created += 1
            saved.append(job)

        await self._session.flush()
        return {"created": created, "updated": updated, "skipped": skipped, "items": saved}

    # ---- Agent 扫描与投递下发 ----
    async def _validate_agent(self, agent_id: str | None) -> str | None:
        cleaned = agent_id.strip() if agent_id and agent_id.strip() else None
        if not cleaned:
            return None
        agent = await AgentService(self._session).get(cleaned)
        if agent.status != AgentStatus.ACTIVE.value:
            raise ValidationError("目标 Agent 已被吊销，无法下发任务")
        return agent.agent_id

    async def dispatch_scan_task(
        self,
        *,
        agent_id: str | None,
        keywords: list[str],
        city: str | None,
        max_jobs: int,
        dry_run: bool,
        timeout_seconds: int,
    ) -> Task:
        pref = await self.get_preference()
        target_agent_id = await self._validate_agent(agent_id)
        final_keywords = [k.strip() for k in keywords if k.strip()] or list(pref.keywords or [])
        if not final_keywords:
            raise ValidationError("请先填写搜索关键词，或在求职偏好中配置默认关键词")
        final_city = (city or "").strip() or (pref.cities[0] if pref.cities else None)

        return await TaskService(self._session).create(
            type_=TaskType.BOSS_SCAN_JOBS,
            agent_id=target_agent_id,
            payload={
                "keywords": final_keywords,
                "city": final_city,
                "max_jobs": max_jobs,
                "dry_run": dry_run,
            },
            priority=8,
            max_attempts=1,
            timeout_seconds=timeout_seconds,
        )

    async def _pick_provider(self, provider_id: int | None, pref: JobPreference) -> AIProvider:
        target_id = provider_id if provider_id is not None else pref.provider_id
        if target_id is not None:
            provider = await self._provider_repo.get_by_id(target_id)
            if provider is None:
                raise NotFoundError("指定的 AI Provider 不存在")
            if not provider.enabled:
                raise ValidationError(f"AI Provider「{provider.name}」已禁用")
            return provider

        for p in await self._provider_repo.list(offset=0, limit=50):
            if p.enabled:
                return p
        raise ValidationError("请先在「AI Providers」中配置并启用至少一个 AI 模型")

    async def score_job_with_ai(
        self,
        job_id: int,
        *,
        provider_id: int | None = None,
        resume_id: int | None = None,
    ) -> BossJob:
        job = await self.get_job(job_id)
        pref = await self.get_preference()

        if resume_id is not None:
            resume = await self._resume_repo.get_by_id(resume_id)
            if resume is None:
                raise NotFoundError("指定的简历不存在")
        else:
            resume = await self._resume_repo.get_active()
            if resume is None:
                raise ValidationError("请先在「简历工作台」创建并激活一份投递简历")

        provider = await self._pick_provider(provider_id, pref)
        api_key = ProviderService.get_decrypted_api_key(provider)
        template_hint = (
            f"\n期望打招呼风格参考：{pref.greeting_template}" if pref.greeting_template else ""
        )
        user_prompt = (
            f"【候选人简历】（{resume.title} / 目标方向：{resume.target_role or '通用'}）\n"
            f"{resume.raw_content[:4000]}\n\n"
            f"【目标岗位】\n"
            f"职位：{job.title}\n公司：{job.company}\n城市：{job.city or '未知'}\n"
            f"薪资：{job.salary or '未知'}\n标签：{', '.join(map(str, job.tags or []))}\n"
            f"JD 描述：\n{job.jd_text[:3000] or '（暂无详细 JD，请结合职位名和标签评估）'}"
            f"{template_hint}"
        )

        raw = await llm_client.complete_json(
            provider=provider,
            api_key=api_key,
            system_prompt=_JOB_SCORE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        try:
            score = max(0, min(100, int(raw.get("match_score", 0))))
        except (TypeError, ValueError):
            score = 0

        job.match_score = score
        job.match_reason = str(raw.get("match_reason") or "").strip()
        job.ai_greeting = str(raw.get("ai_greeting") or "").strip()
        job.resume_id = resume.id
        job.last_error = None
        if job.status in (BossJobStatus.DISCOVERED.value, BossJobStatus.FAILED.value):
            job.status = BossJobStatus.SCORED.value
        await self._session.flush()
        return job

    async def score_jobs_batch(
        self,
        *,
        limit: int = 10,
        provider_id: int | None = None,
        resume_id: int | None = None,
    ) -> dict[str, Any]:
        """批量对未评分（discovered）岗位执行 AI 匹配评分并生成话术。"""
        pref = await self.get_preference()
        if resume_id is not None:
            resume = await self._resume_repo.get_by_id(resume_id)
            if resume is None:
                raise NotFoundError("指定的简历不存在")
        else:
            resume = await self._resume_repo.get_active()
            if resume is None:
                raise ValidationError("请先在「简历工作台」创建并激活一份投递简历")
        await self._pick_provider(provider_id, pref)

        targets = await self._job_repo.list_unscored(limit=limit)
        scored_items: list[BossJob] = []
        errors: list[dict[str, Any]] = []
        for job in targets:
            try:
                updated = await self.score_job_with_ai(
                    job.id, provider_id=provider_id, resume_id=resume.id
                )
                scored_items.append(updated)
            except (AppError, ValidationError) as exc:
                errors.append({"job_id": job.id, "title": job.title, "error": str(exc)})
        return {
            "scored": len(scored_items),
            "failed": len(errors),
            "items": scored_items,
            "errors": errors,
        }

    async def dispatch_apply_task(
        self,
        job_id: int,
        *,
        agent_id: str | None = None,
        greeting: str | None = None,
        dry_run: bool = True,
        timeout_seconds: int = 120,
        is_auto: bool = False,
        scheduled_at: datetime | None = None,
    ) -> dict[str, Any]:
        job = await self.get_job(job_id)
        if job.status in (BossJobStatus.APPLIED.value, BossJobStatus.APPLYING.value):
            raise ValidationError(f"岗位「{job.title}」已处于 {job.status} 状态，跳过重复投递")

        pref = await self.get_preference()
        if not dry_run:
            applied_today = await self._job_repo.count_applied_today()
            if applied_today >= pref.daily_apply_limit:
                raise ValidationError(
                    f"今日投递次数已达上限（{applied_today}/{pref.daily_apply_limit}）"
                )

        target_agent_id = await self._validate_agent(agent_id)
        final_greeting = (
            (greeting or "").strip()
            or (job.ai_greeting or "").strip()
            or (pref.greeting_template or "").strip()
            or f"您好，我对贵司「{job.title}」岗位非常感兴趣，我的过往项目经验与岗位要求高度契合，期待进一步沟通！"
        )

        task = await TaskService(self._session).create(
            type_=TaskType.BOSS_APPLY_JOB,
            agent_id=target_agent_id,
            payload={
                "job_id": job.id,
                "boss_job_id": job.boss_job_id,
                "title": job.title,
                "company": job.company,
                "job_url": job.job_url,
                "greeting": final_greeting,
                "dry_run": dry_run,
                "is_auto": is_auto,
            },
            priority=9 if not is_auto else 6,
            max_attempts=1,
            timeout_seconds=timeout_seconds,
            scheduled_at=scheduled_at,
        )
        job.apply_task_id = task.task_id
        job.ai_greeting = final_greeting
        if not dry_run:
            job.status = BossJobStatus.APPLYING.value
            job.last_error = None
        await self._session.flush()
        return {"job": job, "task": task}

    async def dispatch_auto_apply_batch(
        self,
        *,
        agent_id: str | None = None,
        dry_run: bool = True,
        max_count: int = 5,
    ) -> dict[str, Any]:
        pref = await self.get_preference()
        if not pref.auto_apply_enabled:
            raise ValidationError("当前处于「手动确认模式」，请开启自动投递开关后再执行")

        applied_today = await self._job_repo.count_applied_today()
        remaining = max(0, pref.daily_apply_limit - applied_today)
        if not dry_run and remaining == 0:
            raise ValidationError(f"今日投递已达上限（{applied_today}/{pref.daily_apply_limit}）")

        limit = max_count if dry_run else min(max_count, remaining)
        candidates = await self._job_repo.list_auto_apply_candidates(
            min_score=pref.auto_apply_min_score, limit=limit
        )
        base_time = utcnow()
        dispatched: list[dict[str, Any]] = []
        for idx, candidate in enumerate(candidates):
            scheduled_at: datetime | None = None
            if not dry_run and idx > 0:
                scheduled_at = base_time + timedelta(seconds=idx * pref.apply_interval_seconds)
            res = await self.dispatch_apply_task(
                candidate.id,
                agent_id=agent_id,
                dry_run=dry_run,
                is_auto=True,
                scheduled_at=scheduled_at,
            )
            dispatched.append(
                {
                    "job_id": candidate.id,
                    "title": candidate.title,
                    "company": candidate.company,
                    "match_score": candidate.match_score,
                    "task_id": res["task"].task_id,
                    "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                }
            )
        return {
            "dispatched_count": len(dispatched),
            "dry_run": dry_run,
            "min_score": pref.auto_apply_min_score,
            "items": dispatched,
        }

    async def restore_job(self, job_id: int) -> BossJob:
        """将被忽略或投递失败的岗位恢复为可再次评分/投递状态。"""
        job = await self.get_job(job_id)
        if job.status not in (BossJobStatus.SKIPPED.value, BossJobStatus.FAILED.value):
            raise ValidationError(f"当前状态 {job.status} 无需恢复")
        job.status = (
            BossJobStatus.SCORED.value
            if job.match_score is not None
            else BossJobStatus.DISCOVERED.value
        )
        job.last_error = None
        await self._session.flush()
        return job

    async def skip_job(self, job_id: int) -> BossJob:
        job = await self.get_job(job_id)
        if job.status == BossJobStatus.APPLIED.value:
            raise ValidationError("已投递岗位不可标记为忽略")
        job.status = BossJobStatus.SKIPPED.value
        await self._session.flush()
        return job

    async def handle_apply_result(
        self,
        job_id: int,
        *,
        succeeded: bool,
        result_data: dict[str, Any],
        error_text: str | None,
    ) -> BossJob | None:
        job = await self._job_repo.get_by_id(job_id)
        if job is None:
            return None
        if result_data.get("dry_run") is True:
            await self._session.flush()
            return job

        if (
            succeeded
            and result_data.get("applied") is True
            and not result_data.get("needs_human_action", False)
        ):
            job.status = BossJobStatus.APPLIED.value
            job.applied_at = utcnow()
            job.last_error = None
        else:
            job.status = BossJobStatus.FAILED.value
            job.last_error = (
                str(result_data.get("message") or "").strip()
                or error_text
                or "BOSS 投递未完成，需要人工核对"
            )
        await self._session.flush()
        return job
