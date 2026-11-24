"""业务枚举：任务状态与任务类型。"""
from enum import Enum


class TaskStatus(str, Enum):
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    PING = "PING"
    SYSTEM_INFO = "SYSTEM_INFO"


class AgentStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
