"""审计日志 Schema。"""
from datetime import datetime
from typing import Any

from app.schemas.common import ORMModel


class AuditLogOut(ORMModel):
    id: int
    ts: datetime
    actor: str
    action: str
    target: str
    detail: dict[str, Any]
