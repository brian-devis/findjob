"""简历管理与 AI 审阅改写服务。"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.time import utcnow
from app.models.ai_provider import AIProvider
from app.models.resume import Resume
from app.repositories.provider import AIProviderRepository
from app.repositories.resume import ResumeRepository
from app.services import llm_client
from app.services.provider_service import ProviderService

_REVIEW_SYSTEM_PROMPT = """你是一位资深技术招聘官与简历优化专家，熟悉 BOSS 直聘筛选机制。
请严格输出一个 JSON 对象，不要包含任何多余解释文字。字段格式如下：
{
  "score": 0-100 的整数评分,
  "summary": "整体评价（2-3 句话）",
  "strengths": ["优势1", "优势2"],
  "issues": ["待改进问题1（具体指出缺量化数据/关键词/表达模糊处）"],
  "suggestions": ["可落地的修改建议1"]
}"""

_REWRITE_SYSTEM_PROMPT = """你是一位资深求职顾问，负责将简历改写为更适合 BOSS 直聘展示与 HR 筛选的版本。
要求：保留真实经历与技术栈，不得编造不存在的履历；突出项目职责、量化成果与核心关键词。
请严格输出一个 JSON 对象，不要包含任何多余解释文字：
{
  "title": "优化后的版本标题（如：张三-后端开发-AI优化版）",
  "raw_content": "优化后的完整 Markdown 简历正文",
  "structured_json": {
    "summary": "个人优势/自我评价（可直接用于 BOSS 直聘个人优势栏）",
    "skills": ["核心技能关键词"],
    "work_experiences": [{"company": "", "role": "", "period": "", "highlights": ""}],
    "projects": [{"name": "", "role": "", "highlights": ""}],
    "education": [{"school": "", "major": "", "degree": "", "period": ""}]
  }
}"""


def _normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


class ResumeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ResumeRepository(session)
        self._provider_repo = AIProviderRepository(session)

    async def create(
        self,
        *,
        title: str,
        target_role: str | None,
        source_filename: str | None,
        source_format: str,
        raw_content: str,
        structured_json: dict[str, Any] | None = None,
        parent_id: int | None = None,
    ) -> Resume:
        existing_count = await self._repo.count()
        return await self._repo.create(
            title=title,
            target_role=target_role,
            source_filename=source_filename,
            source_format=source_format,
            raw_content=raw_content,
            structured_json=structured_json,
            parent_id=parent_id,
            is_active=(existing_count == 0),
        )

    async def get(self, resume_id: int) -> Resume:
        resume = await self._repo.get_by_id(resume_id)
        if resume is None:
            raise NotFoundError("简历不存在")
        return resume

    async def list(self, offset: int = 0, limit: int = 50) -> list[Resume]:
        return await self._repo.list(offset=offset, limit=limit)

    async def count(self) -> int:
        return await self._repo.count()

    async def update(
        self,
        resume_id: int,
        *,
        title: str | None = None,
        target_role: str | None = None,
        raw_content: str | None = None,
        structured_json: dict[str, Any] | None = None,
    ) -> Resume:
        resume = await self.get(resume_id)
        if title is not None:
            resume.title = title
        if target_role is not None:
            resume.target_role = target_role.strip() or None
        if raw_content is not None:
            resume.raw_content = raw_content
        if structured_json is not None:
            resume.structured_json = structured_json
        await self._session.flush()
        return resume

    async def activate(self, resume_id: int) -> Resume:
        resume = await self.get(resume_id)
        await self._repo.clear_active()
        resume.is_active = True
        await self._session.flush()
        return resume

    async def delete(self, resume_id: int) -> None:
        resume = await self.get(resume_id)
        was_active = resume.is_active
        await self._repo.delete(resume)
        if was_active:
            remaining = await self._repo.list(offset=0, limit=1)
            if remaining:
                remaining[0].is_active = True
                await self._session.flush()

    async def _pick_provider(self, provider_id: int | None) -> AIProvider:
        if provider_id is not None:
            provider = await self._provider_repo.get_by_id(provider_id)
            if provider is None:
                raise NotFoundError("指定的 AI Provider 不存在")
            if not provider.enabled:
                raise ValidationError(f"AI Provider「{provider.name}」已禁用")
            return provider

        providers = await self._provider_repo.list(offset=0, limit=50)
        for p in providers:
            if p.enabled:
                return p
        raise ValidationError("请先在「AI Providers」中配置并启用至少一个 AI 模型")

    async def review_with_ai(
        self,
        resume_id: int,
        *,
        provider_id: int | None = None,
        target_role: str | None = None,
    ) -> Resume:
        resume = await self.get(resume_id)
        provider = await self._pick_provider(provider_id)
        api_key = ProviderService.get_decrypted_api_key(provider)
        role = (target_role or "").strip() or (resume.target_role or "").strip() or "通用岗位"

        user_prompt = (
            f"目标岗位方向：{role}\n"
            f"简历标题：{resume.title}\n\n"
            f"简历正文：\n{resume.raw_content}"
        )
        raw_json = await llm_client.complete_json(
            provider=provider,
            api_key=api_key,
            system_prompt=_REVIEW_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        raw_score = raw_json.get("score", 0)
        try:
            score = max(0, min(100, int(raw_score)))
        except (TypeError, ValueError):
            score = 0

        resume.ai_review_json = {
            "score": score,
            "summary": str(raw_json.get("summary") or "").strip(),
            "strengths": _normalize_list(raw_json.get("strengths")),
            "issues": _normalize_list(raw_json.get("issues")),
            "suggestions": _normalize_list(raw_json.get("suggestions")),
            "target_role": role,
            "provider_name": provider.name,
            "model": provider.model,
            "reviewed_at": utcnow().isoformat(),
        }
        if target_role and target_role.strip():
            resume.target_role = target_role.strip()
        await self._session.flush()
        return resume

    async def rewrite_with_ai(
        self,
        resume_id: int,
        *,
        provider_id: int | None = None,
        target_role: str | None = None,
        instruction: str | None = None,
    ) -> Resume:
        resume = await self.get(resume_id)
        provider = await self._pick_provider(provider_id)
        api_key = ProviderService.get_decrypted_api_key(provider)
        role = (target_role or "").strip() or (resume.target_role or "").strip() or "通用岗位"

        review_context = ""
        if resume.ai_review_json:
            review_context = (
                "\n\n已有 AI 审阅意见（请重点针对以下问题改进）：\n"
                + json.dumps(resume.ai_review_json, ensure_ascii=False)
            )
        extra = f"\n\n用户补充改写要求：{instruction.strip()}" if instruction and instruction.strip() else ""

        user_prompt = (
            f"目标岗位方向：{role}\n"
            f"原简历标题：{resume.title}\n\n"
            f"原简历正文：\n{resume.raw_content}"
            f"{review_context}{extra}"
        )
        raw_json = await llm_client.complete_json(
            provider=provider,
            api_key=api_key,
            system_prompt=_REWRITE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        new_content = str(raw_json.get("raw_content") or "").strip()
        if not new_content:
            raise ValidationError("AI 改写返回的正文为空，请重试")

        new_title = str(raw_json.get("title") or f"{resume.title}（AI 优化版）").strip()[:128]
        structured = raw_json.get("structured_json")
        if not isinstance(structured, dict):
            structured = {}

        return await self._repo.create(
            title=new_title,
            target_role=role if role != "通用岗位" else resume.target_role,
            source_filename=None,
            source_format="markdown",
            raw_content=new_content,
            structured_json=structured,
            parent_id=resume.id,
            is_active=False,
        )
