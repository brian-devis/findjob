"""在线 Agent WebSocket 连接管理器。"""
import asyncio
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.ws.protocol import WS_CLOSE_GOING_AWAY, WS_CLOSE_NORMAL

logger = get_logger("app.ws.manager")
_WS_ERRORS = (WebSocketDisconnect, RuntimeError, OSError)


class AgentConnectionManager:
    """维护在线 Agent 的 WebSocket 连接映射，提供安全的发送与断开操作。"""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, agent_id: str, websocket: WebSocket) -> None:
        old_ws: WebSocket | None = None
        async with self._lock:
            old_ws = self._connections.get(agent_id)
            self._connections[agent_id] = websocket

        if old_ws is not None and old_ws is not websocket:
            logger.info("Agent %s 重新连接，关闭旧连接", agent_id)
            try:
                await old_ws.close(code=WS_CLOSE_NORMAL, reason="replaced by new connection")
            except _WS_ERRORS as exc:
                logger.debug("关闭 Agent %s 旧连接时忽略异常: %s", agent_id, exc)

    async def disconnect(self, agent_id: str, websocket: WebSocket | None = None) -> None:
        async with self._lock:
            current = self._connections.get(agent_id)
            if current is None:
                return
            if websocket is None or current is websocket:
                self._connections.pop(agent_id, None)

    def is_online(self, agent_id: str) -> bool:
        return agent_id in self._connections

    def online_agent_ids(self) -> list[str]:
        return list(self._connections.keys())

    async def send_json(self, agent_id: str, payload: dict[str, Any]) -> bool:
        async with self._lock:
            websocket = self._connections.get(agent_id)
        if websocket is None:
            return False
        try:
            await websocket.send_json(payload)
            return True
        except _WS_ERRORS as exc:
            logger.warning("向 Agent %s 发送消息失败: %s", agent_id, exc)
            await self.disconnect(agent_id, websocket)
            return False

    async def disconnect_agent(
        self, agent_id: str, code: int = WS_CLOSE_NORMAL, reason: str = ""
    ) -> bool:
        async with self._lock:
            websocket = self._connections.pop(agent_id, None)
        if websocket is None:
            return False
        try:
            await websocket.close(code=code, reason=reason)
        except _WS_ERRORS as exc:
            logger.debug("主动断开 Agent %s 时忽略异常: %s", agent_id, exc)
        return True

    async def close_all(
        self, code: int = WS_CLOSE_GOING_AWAY, reason: str = "server shutdown"
    ) -> None:
        async with self._lock:
            items = list(self._connections.items())
            self._connections.clear()
        for agent_id, websocket in items:
            try:
                await websocket.close(code=code, reason=reason)
            except _WS_ERRORS as exc:
                logger.debug("关闭 Agent %s 连接时忽略异常: %s", agent_id, exc)


ws_manager = AgentConnectionManager()
