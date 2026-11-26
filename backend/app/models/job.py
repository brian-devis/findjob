"""求职偏好配置与扫描岗位/投递漏斗模型。"""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import BossJobStatus
from app.models.base import Base, TimestampMixin


class JobPreference(Base, TimestampMixin):
    __tablename__ = "job_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    cities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exclude_companies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    exclude_keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    auto_apply_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_apply_min_score: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    daily_apply_limit: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    apply_interval_seconds: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    greeting_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class BossJob(Base, TimestampMixin):
    __tablename__ = "boss_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    boss_job_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    salary: Mapped[str | None] = mapped_column(String(64), nullable=True)
    experience: Mapped[str | None] = mapped_column(String(64), nullable=True)
    education: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recruiter: Mapped[str | None] = mapped_column(String(128), nullable=True)
    job_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    jd_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    match_score: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    match_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_greeting: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=BossJobStatus.DISCOVERED.value, index=True, nullable=False
    )
    resume_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    apply_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
