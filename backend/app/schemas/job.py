"""求职偏好、岗位扫描与投递漏斗 Schema。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


def _clean_str_list(items: list[str] | None) -> list[str]:
    if not items:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        s = str(item).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


class JobPreferenceOut(ORMModel):
    id: int
    keywords: list[str]
    cities: list[str]
    salary_min: int | None = None
    salary_max: int | None = None
    exclude_companies: list[str]
    exclude_keywords: list[str]
    auto_apply_enabled: bool
    auto_apply_min_score: int
    daily_apply_limit: int
    apply_interval_seconds: int
    greeting_template: str | None = None
    provider_id: int | None = None
    updated_at: datetime


class JobPreferenceUpdate(BaseModel):
    keywords: list[str] = Field(default_factory=list, max_length=20)
    cities: list[str] = Field(default_factory=list, max_length=20)
    salary_min: int | None = Field(default=None, ge=0, le=500)
    salary_max: int | None = Field(default=None, ge=0, le=1000)
    exclude_companies: list[str] = Field(default_factory=list, max_length=50)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=50)
    auto_apply_enabled: bool = False
    auto_apply_min_score: int = Field(default=80, ge=0, le=100)
    daily_apply_limit: int = Field(default=30, ge=1, le=200)
    apply_interval_seconds: int = Field(default=45, ge=5, le=600)
    greeting_template: str | None = Field(default=None, max_length=1000)
    provider_id: int | None = None

    @model_validator(mode="after")
    def _validate_ranges(self) -> "JobPreferenceUpdate":
        self.keywords = _clean_str_list(self.keywords)
        self.cities = _clean_str_list(self.cities)
        self.exclude_companies = _clean_str_list(self.exclude_companies)
        self.exclude_keywords = _clean_str_list(self.exclude_keywords)
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("最低薪资不能高于最高薪资")
        return self


class BossJobOut(ORMModel):
    id: int
    boss_job_id: str
    title: str
    company: str
    city: str | None = None
    salary: str | None = None
    experience: str | None = None
    education: str | None = None
    recruiter: str | None = None
    job_url: str | None = None
    jd_text: str
    tags: list[Any]
    match_score: int | None = None
    match_reason: str | None = None
    ai_greeting: str | None = None
    status: str
    resume_id: int | None = None
    apply_task_id: str | None = None
    last_error: str | None = None
    applied_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BossJobImportItem(BaseModel):
    boss_job_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    city: str | None = Field(default=None, max_length=64)
    salary: str | None = Field(default=None, max_length=64)
    experience: str | None = Field(default=None, max_length=64)
    education: str | None = Field(default=None, max_length=64)
    recruiter: str | None = Field(default=None, max_length=128)
    job_url: str | None = Field(default=None, max_length=512)
    jd_text: str = Field(default="", max_length=20000)
    tags: list[str] = Field(default_factory=list, max_length=20)


class BossJobImportRequest(BaseModel):
    items: list[BossJobImportItem] = Field(min_length=1, max_length=100)


class BossJobScanRequest(BaseModel):
    agent_id: str | None = Field(default=None, max_length=64)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    city: str | None = Field(default=None, max_length=64)
    max_jobs: int = Field(default=20, ge=1, le=50)
    dry_run: bool = False
    timeout_seconds: int = Field(default=180, ge=15, le=600)


class BossJobScoreRequest(BaseModel):
    provider_id: int | None = None
    resume_id: int | None = None


class BossJobBatchScoreRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=30)
    provider_id: int | None = None
    resume_id: int | None = None


class BossJobApplyRequest(BaseModel):
    agent_id: str | None = Field(default=None, max_length=64)
    greeting: str | None = Field(default=None, max_length=1000)
    dry_run: bool = True
    timeout_seconds: int = Field(default=120, ge=15, le=600)


class BossJobAutoApplyRequest(BaseModel):
    agent_id: str | None = Field(default=None, max_length=64)
    dry_run: bool = True
    max_count: int = Field(default=5, ge=1, le=30)
