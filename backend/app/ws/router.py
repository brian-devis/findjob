"""Agent WebSocket 端点：鉴权、心跳、任务确认与结果回传。"""
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError as PydanticValidationError

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.enums import AgentStatus, TaskStatus, TaskType
from app.core.logging import get_logger
from app.core.security import verify_password
from app.core.time import utcnow
from app.repositories.agent import AgentRepository
from app.repositories.resume import ResumeRepository
from app.services.job_service import JobService
from app.services.task_service import TaskService
from app.ws.manager import ws_manager
from app.ws.protocol import (
    WS_CLOSE_AGENT_REVOKED,
    WS_CLOSE_AUTH_FAILED,
    WS_CLOSE_HEARTBEAT_TIMEOUT,
    WS_CLOSE_PROTOCOL_ERROR,
    TaskAckData,
    TaskProgressData,
    TaskResultData,
    WSMessage,
    make_message,
)

logger = get_logger("app.ws.router")
router = APIRouter()


def _get_session_factory(websocket: WebSocket):
    return getattr(websocket.app.state, "session_factory", None) or async_session_factory


def _trigger_scheduler(websocket: WebSocket) -> None:
    scheduler = getattr(websocket.app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.trigger()


def _extract_auth_headers(websocket: WebSocket) -> tuple[str | None, str | None]:
    agent_id = websocket.headers.get("x-agent-id")
    auth_header = websocket.headers.get("authorization")
    if not agent_id or not auth_header:
        return None, None
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None, None
    return agent_id.strip(), token.strip()


async def _authenticate(websocket: WebSocket) -> str | None:
    """校验握手请求头；失败时发送 auth_error 并以对应关闭码断开。"""
    agent_id, secret = _extract_auth_headers(websocket)
    if not agent_id or not secret:
        await websocket.send_json(
            make_message("auth_error", {"reason": "missing or invalid auth headers"})
        )
        await websocket.close(code=WS_CLOSE_AUTH_FAILED, reason="auth failed")
        return None

    session_factory = _get_session_factory(websocket)
    async with session_factory() as session:
        repo = AgentRepository(session)
        agent = await repo.get_by_agent_id(agent_id)
        if agent is None:
            logger.warning("WS 鉴权失败：未知 Agent %s", agent_id)
            await websocket.send_json(
                make_message("auth_error", {"reason": "invalid credentials"})
            )
            await websocket.close(code=WS_CLOSE_AUTH_FAILED, reason="auth failed")
            return None

        if not verify_password(secret, agent.secret_hash):
            logger.warning("WS 鉴权失败：Agent %s 凭据不匹配", agent_id)
            await websocket.send_json(
                make_message("auth_error", {"reason": "invalid credentials"})
            )
            await websocket.close(code=WS_CLOSE_AUTH_FAILED, reason="auth failed")
            return None

        if agent.status == AgentStatus.REVOKED.value:
            logger.warning("WS 拒绝连接：Agent %s 已被吊销", agent_id)
            await websocket.send_json(make_message("auth_error", {"reason": "agent revoked"}))
            await websocket.close(code=WS_CLOSE_AGENT_REVOKED, reason="agent revoked")
            return None

        await repo.touch_last_seen(agent_id, utcnow())
        await session.commit()

    return agent_id


async def _touch_last_seen(websocket: WebSocket, agent_id: str) -> None:
    session_factory = _get_session_factory(websocket)
    async with session_factory() as session:
        await AgentRepository(session).touch_last_seen(agent_id, utcnow())
        await session.commit()


async def _handle_task_ack(websocket: WebSocket, agent_id: str, msg: WSMessage) -> None:
    try:
        data = TaskAckData.model_validate(msg.data)
    except PydanticValidationError:
        await websocket.send_json(
            make_message("error", {"code": "INVALID_PAYLOAD", "message": "invalid task_ack data"}, msg.id)
        )
        return

    session_factory = _get_session_factory(websocket)
    async with session_factory() as session:
        service = TaskService(session)
        task = await service._repo.get_by_task_id(data.task_id)
        if task is None or task.agent_id != agent_id:
            await websocket.send_json(
                make_message("error", {"code": "TASK_NOT_FOUND", "message": "task not found"}, msg.id)
            )
            return

        if task.status_enum == TaskStatus.DISPATCHED:
            await service.ack(task)
            await session.commit()
            logger.info("Agent %s 确认任务 %s 开始执行", agent_id, task.task_id)
        elif task.status_enum == TaskStatus.RUNNING or service.is_terminal(task):
            logger.debug("忽略重复 task_ack：task=%s status=%s", task.task_id, task.status)
        else:
            await websocket.send_json(
                make_message(
                    "error",
                    {"code": "INVALID_STATE", "message": f"task status is {task.status}"},
                    msg.id,
                )
            )


async def _handle_task_result(websocket: WebSocket, agent_id: str, msg: WSMessage) -> None:
    try:
        data = TaskResultData.model_validate(msg.data)
    except PydanticValidationError:
        await websocket.send_json(
            make_message(
                "error", {"code": "INVALID_PAYLOAD", "message": "invalid task_result data"}, msg.id
            )
        )
        return

    requeued = False
    session_factory = _get_session_factory(websocket)
    async with session_factory() as session:
        service = TaskService(session)
        task = await service._repo.get_by_task_id(data.task_id)
        if task is None or task.agent_id != agent_id:
            await websocket.send_json(
                make_message("error", {"code": "TASK_NOT_FOUND", "message": "task not found"}, msg.id)
            )
            return

        # 结果去重：终态任务直接忽略
        if service.is_terminal(task):
            logger.info("忽略终态任务重复结果：task=%s status=%s", task.task_id, task.status)
            return

        # 容错：若 ack 丢失但结果已到达，先转为 running 再完成
        if task.status_enum == TaskStatus.DISPATCHED:
            await service.ack(task)

        if task.status_enum != TaskStatus.RUNNING:
            await websocket.send_json(
                make_message(
                    "error",
                    {"code": "INVALID_STATE", "message": f"task status is {task.status}"},
                    msg.id,
                )
            )
            return

        succeeded = data.status == "succeeded"
        task = await service.complete(
            task,
            succeeded=succeeded,
            result=data.result,
            error=data.error,
        )
        if task.type == TaskType.BOSS_SYNC_RESUME.value and succeeded:
            res_data = data.result if isinstance(data.result, dict) else {}
            if (
                res_data.get("synced") is True
                and res_data.get("dry_run") is False
                and not res_data.get("needs_human_action", False)
            ):
                resume_id = (task.payload or {}).get("resume_id")
                if isinstance(resume_id, int) and not isinstance(resume_id, bool):
                    resume = await ResumeRepository(session).get_by_id(resume_id)
                    if resume is not None:
                        resume.synced_to_boss_at = utcnow()
                        await session.flush()
        elif task.type == TaskType.BOSS_SCAN_JOBS.value and succeeded:
            res_data = data.result if isinstance(data.result, dict) else {}
            raw_jobs = res_data.get("jobs")
            if isinstance(raw_jobs, list) and raw_jobs:
                await JobService(session).ingest_jobs(raw_jobs)
        elif task.type == TaskType.BOSS_APPLY_JOB.value:
            res_data = data.result if isinstance(data.result, dict) else {}
            job_id = (task.payload or {}).get("job_id")
            if isinstance(job_id, int) and not isinstance(job_id, bool):
                await JobService(session).handle_apply_result(
                    job_id,
                    succeeded=succeeded,
                    result_data=res_data,
                    error_text=data.error,
                )
        requeued = task.status_enum == TaskStatus.QUEUED
        await session.commit()
        logger.info(
            "Agent %s 上报任务 %s 结果：%s -> status=%s",
            agent_id,
            task.task_id,
            data.status,
            task.status,
        )

    if requeued:
        _trigger_scheduler(websocket)


async def _handle_task_progress(websocket: WebSocket, agent_id: str, msg: WSMessage) -> None:
    try:
        data = TaskProgressData.model_validate(msg.data)
    except PydanticValidationError:
        await websocket.send_json(
            make_message(
                "error", {"code": "INVALID_PAYLOAD", "message": "invalid task_progress data"}, msg.id
            )
        )
        return
    session_factory = _get_session_factory(websocket)
    async with session_factory() as session:
        task = await TaskService(session)._repo.get_by_task_id(data.task_id)
        if task is None or task.agent_id != agent_id:
            await websocket.send_json(
                make_message("error", {"code": "TASK_NOT_FOUND", "message": "task not found"}, msg.id)
            )
            return
    logger.debug("Agent %s 上报任务 %s 进度", agent_id, data.task_id)


@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    agent_id = await _authenticate(websocket)
    if agent_id is None:
        return

    await ws_manager.connect(agent_id, websocket)
    await websocket.send_json(make_message("auth_ok", {"agent_id": agent_id}))
    logger.info("Agent %s 已建立 WebSocket 连接", agent_id)
    _trigger_scheduler(websocket)

    settings = get_settings()
    loop = asyncio.get_running_loop()
    last_activity = loop.time()

    async def _heartbeat_loop() -> None:
        missed = 0
        interval = settings.ws_heartbeat_interval_seconds
        timeout = settings.ws_heartbeat_timeout_seconds
        max_missed = settings.ws_heartbeat_max_missed

        while True:
            await asyncio.sleep(interval)
            now_mono = loop.time()
            if now_mono - last_activity < interval:
                missed = 0
                continue

            ping_sent_at = loop.time()
            try:
                await websocket.send_json(make_message("ping", {}))
            except (WebSocketDisconnect, RuntimeError, OSError):
                return

            await asyncio.sleep(timeout)
            if last_activity >= ping_sent_at:
                missed = 0
            else:
                missed += 1
                logger.warning("Agent %s 心跳超时 (%d/%d)", agent_id, missed, max_missed)
                if missed >= max_missed:
                    try:
                        await websocket.close(
                            code=WS_CLOSE_HEARTBEAT_TIMEOUT, reason="heartbeat timeout"
                        )
                    except (WebSocketDisconnect, RuntimeError, OSError) as exc:
                        logger.debug("心跳超时关闭 Agent %s 时忽略异常: %s", agent_id, exc)
                    return

    heartbeat_task = asyncio.create_task(_heartbeat_loop())
    try:
        while True:
            raw_text = await websocket.receive_text()
            last_activity = loop.time()

            try:
                raw_obj = json.loads(raw_text)
                msg = WSMessage.model_validate(raw_obj)
            except (json.JSONDecodeError, PydanticValidationError):
                await websocket.send_json(
                    make_message("error", {"code": "PROTOCOL_ERROR", "message": "invalid message format"})
                )
                await websocket.close(code=WS_CLOSE_PROTOCOL_ERROR, reason="protocol error")
                break

            if msg.type == "ping":
                await _touch_last_seen(websocket, agent_id)
                await websocket.send_json(make_message("pong", {}, msg.id))
            elif msg.type == "pong":
                await _touch_last_seen(websocket, agent_id)
            elif msg.type == "task_ack":
                await _handle_task_ack(websocket, agent_id, msg)
            elif msg.type == "task_result":
                await _handle_task_result(websocket, agent_id, msg)
            elif msg.type == "task_progress":
                await _handle_task_progress(websocket, agent_id, msg)
            else:
                await websocket.send_json(
                    make_message(
                        "error",
                        {"code": "UNKNOWN_TYPE", "message": f"unsupported type: {msg.type}"},
                        msg.id,
                    )
                )
    except WebSocketDisconnect:
        logger.info("Agent %s 断开 WebSocket 连接", agent_id)
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await ws_manager.disconnect(agent_id, websocket)
