"""时间工具：统一使用 UTC。"""
from datetime import UTC, datetime


def utcnow() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(UTC)
