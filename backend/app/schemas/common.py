"""通用 schema：统一响应格式与 ORM 基类。"""
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, field_serializer

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应包裹：code=0 表示成功。"""

    code: int = 0
    message: str = "success"
    data: T | None = None


def ok(data: Any = None, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data}


def err(code: int, message: str) -> dict:
    return {"code": code, "message": message, "data": None}


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer(
        "created_at",
        "updated_at",
        "dispatched_at",
        "started_at",
        "finished_at",
        "lease_expires_at",
        "scheduled_at",
        "revoked_at",
        "last_seen_at",
        check_fields=False,
    )
    def _serialize_datetime(self, value: datetime | None) -> datetime | None:
        return _ensure_utc(value)
