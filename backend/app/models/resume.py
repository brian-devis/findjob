"""简历模型：存储原始/改写版本、结构化信息与 AI 审阅结论。"""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Resume(Base, TimestampMixin):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    target_role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_format: Mapped[str] = mapped_column(String(16), default="markdown", nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    ai_review_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    synced_to_boss_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
