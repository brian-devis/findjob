"""简历相关 Schema。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


def _strip_non_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        raise ValueError("字段不能为空白字符串")
    return stripped


class ResumeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    target_role: str | None = Field(default=None, max_length=128)
    source_format: str = Field(default="markdown", max_length=16)
    raw_content: str = Field(min_length=1)
    structured_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "raw_content")
    @classmethod
    def _check_required(cls, v: str) -> str:
        res = _strip_non_blank(v)
        assert res is not None
        return res


class ResumeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    target_role: str | None = Field(default=None, max_length=128)
    raw_content: str | None = Field(default=None, min_length=1)
    structured_json: dict[str, Any] | None = None

    @field_validator("title", "raw_content")
    @classmethod
    def _check_optional(cls, v: str | None) -> str | None:
        return _strip_non_blank(v)


class ResumeAIRequest(BaseModel):
    provider_id: int | None = None
    target_role: str | None = Field(default=None, max_length=128)
    instruction: str | None = Field(default=None, max_length=1000)


class ResumeSyncBossRequest(BaseModel):
    agent_id: str | None = Field(default=None, max_length=64)
    dry_run: bool = True
    timeout_seconds: int = Field(default=180, ge=15, le=600)


class ResumeSummaryOut(ORMModel):
    id: int
    title: str
    target_role: str | None = None
    source_filename: str | None = None
    source_format: str
    parent_id: int | None = None
    is_active: bool
    ai_review_json: dict[str, Any] | None = None
    synced_to_boss_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ResumeOut(ResumeSummaryOut):
    raw_content: str
    structured_json: dict[str, Any]
