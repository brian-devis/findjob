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
    BOSS_CHECK_LOGIN = "BOSS_CHECK_LOGIN"
    BOSS_SYNC_RESUME = "BOSS_SYNC_RESUME"
    BOSS_SCAN_JOBS = "BOSS_SCAN_JOBS"
    BOSS_APPLY_JOB = "BOSS_APPLY_JOB"


class AgentStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class BossJobStatus(str, Enum):
    DISCOVERED = "discovered"
    SCORED = "scored"
    APPROVED = "approved"
    APPLYING = "applying"
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"
