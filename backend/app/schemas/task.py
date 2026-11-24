"""任务相关 schema。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import TaskStatus, TaskType
from app.schemas.common import ORMModel


class TaskCreate(BaseModel):
    type: TaskType
    agent_id: str | None = Field(default=None, max_length=36)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=1, ge=1, le=10)
    timeout_seconds: int = Field(default=300, ge=1, le=86400)
    idempotency_key: str | None = Field(default=None, max_length=64)
    scheduled_at: datetime | None = None


class TaskOut(ORMModel):
    task_id: str
    agent_id: str | None = None
    type: str
    status: str
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    priority: int
    attempt: int
    max_attempts: int
    timeout_seconds: int
    idempotency_key: str | None = None
    created_at: datetime
    dispatched_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int


class TaskStatusOut(BaseModel):
    task_id: str
    status: TaskStatus
    attempt: int
