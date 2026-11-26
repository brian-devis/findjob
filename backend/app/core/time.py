"""时间工具：统一使用 UTC。"""
from datetime import UTC, datetime


def utcnow() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """将数据库读出的 datetime 标准化为带 UTC 时区的 aware datetime。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
