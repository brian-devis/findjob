"""AI Provider 模型。"""
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AIProvider(Base, TimestampMixin):
    __tablename__ = "ai_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    api_format: Mapped[str] = mapped_column(String(16), default="openai", nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
