"""Windows Local Agent WebSocket 客户端。

协议规范见 docs/websocket-protocol.md：
- 握手鉴权：X-Agent-Id + Authorization: Bearer <secret>
- 心跳保活：定期发送 ping，响应服务端 ping，超时断线重连
- 幂等与补报：以本地 TaskExecutionStore 落盘 task_id 结果，断线重连后自动补报
- 指数退避 + 抖动重连（4001/4002 鉴权/吊销错误不重试）
"""
import asyncio
import json
import logging
import random
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from agent.config import AgentSettings
from agent.executors import TaskExecutorRegistry
from agent.store import TaskExecutionStore, TaskRecord

logger = logging.getLogger("agent.client")

WS_CLOSE_AUTH_FAILED = 4001
WS_CLOSE_AGENT_REVOKED = 4002
_NON_RETRYABLE_CLOSE_CODES = {WS_CLOSE_AUTH_FAILED, WS_CLOSE_AGENT_REVOKED}


class AgentAuthError(RuntimeError):
    """鉴权失败或 Agent 已被吊销（不可通过重连恢复）。"""


def compute_backoff(attempt: int, base: float = 1.0, cap: float = 60.0) -> float:
    """计算带 ±20% 抖动的指数退避秒数。"""
    exp = min(cap, base * (2 ** max(0, attempt - 1)))
    jitter = random.uniform(0.8, 1.2)
    return min(cap, exp * jitter)


def make_message(
    msg_type: str,
    data: dict[str, Any] | None = None,
    msg_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": msg_type, "data": data or {}}
    if msg_id is not None:
        payload["id"] = msg_id
    return payload


class LocalAgentClient:
    def __init__(
        self,
        settings: AgentSettings,
        *,
        store: TaskExecutionStore | None = None,
        registry: TaskExecutorRegistry | None = None,
    ) -> None:
        self._settings = settings
        self._store = store or TaskExecutionStore(settings.state_db_path)
        self._owns_store = store is None
        self._registry = registry or TaskExecutorRegistry()
        self._stop_event = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._active_ws: Any = None
        self._running_tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def store(self) -> TaskExecutionStore:
        return self._store

    def stop(self) -> None:
        """请求客户端优雅停止。"""
        self._stop_event.set()

    async def close(self) -> None:
        self.stop()
        for task in list(self._running_tasks.values()):
            task.cancel()
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)
            self._running_tasks.clear()
        if self._active_ws is not None:
            try:
                await self._active_ws.close(code=1001, reason="agent shutdown")
            except (WebSocketException, OSError, RuntimeError):
                pass
            self._active_ws = None
        if self._owns_store:
            self._store.close()

    async def _send_json(self, ws: Any, payload: dict[str, Any]) -> bool:
        if ws is None:
            return False
        async with self._send_lock:
            try:
                await ws.send(json.dumps(payload, ensure_ascii=False))
                return True
            except (WebSocketException, OSError, RuntimeError) as exc:
                logger.warning("发送消息失败（type=%s）: %s", payload.get("type"), exc)
                return False

    async def _report_record(self, ws: Any, record: TaskRecord) -> bool:
        data: dict[str, Any] = {
            "task_id": record.task_id,
            "status": record.status,
        }
        if record.result is not None:
            data["result"] = record.result
        if record.error is not None:
            data["error"] = record.error
        sent = await self._send_json(ws, make_message("task_result", data))
        if sent:
            self._store.mark_reported(record.task_id)
            logger.info("已上报任务 %s 结果（status=%s）", record.task_id, record.status)
        return sent

    async def _flush_unreported(self, ws: Any) -> None:
        unreported = self._store.list_unreported()
        for record in unreported:
            if not await self._report_record(ws, record):
                break

    async def _execute_and_report(
        self,
        task_id: str,
        task_type: str,
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> None:
        try:
            result = await self._registry.execute(
                task_type, payload, timeout_seconds=timeout_seconds
            )
            record = self._store.save_result(
                task_id=task_id,
                status="succeeded",
                result=result,
                error=None,
                reported=False,
            )
        except asyncio.CancelledError:
            logger.info("任务 %s 已被取消", task_id)
            raise
        except TimeoutError:
            record = self._store.save_result(
                task_id=task_id,
                status="failed",
                result=None,
                error=f"local execution timed out after {timeout_seconds}s",
                reported=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("任务 %s 执行失败: %s", task_id, exc)
            record = self._store.save_result(
                task_id=task_id,
                status="failed",
                result=None,
                error=str(exc),
                reported=False,
            )
        finally:
            self._running_tasks.pop(task_id, None)

        if self._active_ws is not None:
            await self._report_record(self._active_ws, record)

    async def handle_message(self, ws: Any, raw_text: str) -> None:
        """处理单条来自服务端的 JSON 文本帧。"""
        try:
            msg = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("收到非法 JSON 消息，忽略")
            return

        if not isinstance(msg, dict):
            return
        msg_type = msg.get("type")
        msg_id = msg.get("id")
        data = msg.get("data") or {}

        if msg_type == "ping":
            await self._send_json(ws, make_message("pong", {}, msg_id))
        elif msg_type == "pong":
            return
        elif msg_type == "task_dispatch":
            await self._handle_task_dispatch(ws, data)
        elif msg_type == "task_cancel":
            task_id = data.get("task_id")
            if isinstance(task_id, str):
                running = self._running_tasks.get(task_id)
                if running is not None and not running.done():
                    running.cancel()
        elif msg_type == "error":
            logger.warning(
                "服务端返回协议错误: code=%s message=%s",
                data.get("code"),
                data.get("message"),
            )
        else:
            logger.debug("忽略未知服务端消息类型: %s", msg_type)

    async def _handle_task_dispatch(self, ws: Any, data: dict[str, Any]) -> None:
        task_id = data.get("task_id")
        task_type = data.get("type")
        payload = data.get("payload") or {}
        timeout_seconds = int(data.get("timeout_seconds") or 300)

        if not isinstance(task_id, str) or not isinstance(task_type, str):
            logger.warning("收到缺少 task_id 或 type 的 task_dispatch，忽略")
            return

        # 1. 本地持久化去重：已完成任务不重复执行，直接重发已有结果
        existing = self._store.get(task_id)
        if existing is not None:
            logger.info("任务 %s 已在本地完成，跳过重复执行并重发结果", task_id)
            await self._report_record(ws, existing)
            return

        # 2. 若正在执行中（如上次 ack 丢失触发重发），仅重发 task_ack
        running = self._running_tasks.get(task_id)
        if running is not None and not running.done():
            logger.info("任务 %s 正在执行中，重发 task_ack", task_id)
            await self._send_json(ws, make_message("task_ack", {"task_id": task_id}))
            return

        # 3. 新任务：先确认接收，再异步执行
        await self._send_json(ws, make_message("task_ack", {"task_id": task_id}))
        logger.info("接收任务 %s（type=%s, timeout=%ds）", task_id, task_type, timeout_seconds)
        self._running_tasks[task_id] = asyncio.create_task(
            self._execute_and_report(task_id, task_type, payload, timeout_seconds),
            name=f"agent-task-{task_id}",
        )

    async def _heartbeat_loop(self, ws: Any) -> None:
        interval = self._settings.heartbeat_interval_seconds
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                return
            except TimeoutError:
                pass
            if not await self._send_json(ws, make_message("ping", {})):
                return

    async def run_once(self) -> None:
        """建立一次 WebSocket 会话直到断开或被请求停止。"""
        headers = {
            "X-Agent-Id": self._settings.agent_id,
            "Authorization": f"Bearer {self._settings.agent_secret}",
        }
        logger.info(
            "正在连接中心服务 %s（agent_id=%s, secret=%s）",
            self._settings.server_ws_url,
            self._settings.agent_id,
            self._settings.masked_secret,
        )

        async with websockets.connect(
            self._settings.server_ws_url,
            additional_headers=headers,
            ping_interval=None,
        ) as ws:
            # 等待首条 auth_ok / auth_error
            try:
                first_raw = await asyncio.wait_for(
                    ws.recv(), timeout=self._settings.recv_timeout_seconds
                )
            except ConnectionClosed as exc:
                if exc.rcvd is not None and exc.rcvd.code in _NON_RETRYABLE_CLOSE_CODES:
                    raise AgentAuthError(f"server closed with code {exc.rcvd.code}") from exc
                raise

            first_msg = json.loads(first_raw)
            if first_msg.get("type") == "auth_error":
                reason = (first_msg.get("data") or {}).get("reason", "auth failed")
                raise AgentAuthError(f"authentication rejected: {reason}")
            if first_msg.get("type") != "auth_ok":
                raise RuntimeError(f"unexpected handshake message: {first_msg.get('type')}")

            self._active_ws = ws
            logger.info("Agent %s 鉴权成功，进入在线监听", self._settings.agent_id)
            await self._flush_unreported(ws)

            heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
            try:
                while not self._stop_event.is_set():
                    try:
                        raw_text = await asyncio.wait_for(
                            ws.recv(), timeout=self._settings.recv_timeout_seconds
                        )
                    except TimeoutError:
                        logger.warning("长时间未收到服务端消息，主动断开并重连")
                        await ws.close(code=1001, reason="receive timeout")
                        break
                    if isinstance(raw_text, bytes):
                        raw_text = raw_text.decode("utf-8", errors="replace")
                    await self.handle_message(ws, raw_text)
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
                self._active_ws = None

    async def run_forever(self) -> None:
        """持续运行并在断线时按指数退避 + 抖动自动重连。"""
        attempt = 0
        while not self._stop_event.is_set():
            try:
                await self.run_once()
                attempt = 0
            except AgentAuthError as exc:
                logger.error("鉴权失败，停止重连: %s", exc)
                raise
            except (ConnectionClosed, WebSocketException, OSError, RuntimeError) as exc:
                if isinstance(exc, ConnectionClosed) and (
                    exc.rcvd is not None and exc.rcvd.code in _NON_RETRYABLE_CLOSE_CODES
                ):
                    logger.error("连接被服务端以关闭码 %s 拒绝，停止重连", exc.rcvd.code)
                    raise AgentAuthError(f"closed with code {exc.rcvd.code}") from exc
                attempt += 1
                delay = compute_backoff(
                    attempt,
                    base=self._settings.reconnect_base_seconds,
                    cap=self._settings.reconnect_max_seconds,
                )
                logger.warning("连接断开（%s），%.1fs 后进行第 %d 次重连", exc, delay, attempt)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                except TimeoutError:
                    pass
