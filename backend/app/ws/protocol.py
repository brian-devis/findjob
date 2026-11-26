"""WebSocket 协议常量与消息 Schema（见 docs/websocket-protocol.md）。"""
from typing import Any, Literal

from pydantic import BaseModel, Field

# WebSocket 关闭码
WS_CLOSE_NORMAL = 1000
WS_CLOSE_GOING_AWAY = 1001
WS_CLOSE_AUTH_FAILED = 4001
WS_CLOSE_AGENT_REVOKED = 4002
WS_CLOSE_HEARTBEAT_TIMEOUT = 4003
WS_CLOSE_PROTOCOL_ERROR = 4004


class WSMessage(BaseModel):
    """通用消息封装。"""

    type: str = Field(min_length=1, max_length=64)
    id: str | None = Field(default=None, max_length=64)
    data: dict[str, Any] = Field(default_factory=dict)


class TaskAckData(BaseModel):
    task_id: str = Field(min_length=1, max_length=36)


class TaskResultData(BaseModel):
    task_id: str = Field(min_length=1, max_length=36)
    status: Literal["succeeded", "failed"]
    result: dict[str, Any] | None = None
    error: str | None = None


class TaskProgressData(BaseModel):
    task_id: str = Field(min_length=1, max_length=36)
    progress: float | int | str | dict[str, Any]


def make_message(
    msg_type: str,
    data: dict[str, Any] | None = None,
    msg_id: str | None = None,
) -> dict[str, Any]:
    """构造标准下发消息字典。"""
    payload: dict[str, Any] = {"type": msg_type, "data": data or {}}
    if msg_id is not None:
        payload["id"] = msg_id
    return payload
