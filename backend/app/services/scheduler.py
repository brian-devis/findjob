"""后台任务调度与恢复循环。

职责：
1. 回收已过期的 dispatched 租约（回到 queued 重分配）；
2. 回收执行超时的 running 任务（按 max_attempts 自动重试或进入 failed 终态，并通知 Agent 取消）；
3. 将就绪的 queued 任务分发给在线 Agent，下发失败时立即回滚入队。
"""
import asyncio
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.core.time import ensure_utc, utcnow
from app.repositories.task import TaskRepository
from app.services.task_service import TaskService
from app.ws.manager import AgentConnectionManager
from app.ws.protocol import make_message

logger = get_logger("app.services.scheduler")


class TaskScheduler:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        ws_manager: AgentConnectionManager,
        poll_interval_seconds: float = 2.0,
        dispatch_lease_seconds: int = 30,
    ) -> None:
        self._session_factory = session_factory
        self._ws_manager = ws_manager
        self._poll_interval = poll_interval_seconds
        self._lease_seconds = dispatch_lease_seconds
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._rr_cursor = 0

    def trigger(self) -> None:
        """事件驱动立即唤醒调度循环（如新任务入队或 Agent 上线）。"""
        self._wake_event.set()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="aijob-task-scheduler")
        logger.info("任务调度循环已启动（poll=%.1fs, lease=%ds）", self._poll_interval, self._lease_seconds)

    async def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("任务调度循环已停止")

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._wake_event.clear()
            try:
                await self.run_once()
            except Exception:
                logger.exception("任务调度周期异常")

            if not self._wake_event.is_set():
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=self._poll_interval)
                except TimeoutError:
                    pass

    async def run_once(self) -> dict[str, int]:
        """执行一次完整的回收 + 超时检查 + 分发周期。"""
        requeued = await self.reclaim_expired_leases()
        timed_out = await self.timeout_running_tasks()
        dispatched = await self.dispatch_queued_tasks()
        return {"requeued": requeued, "timed_out": timed_out, "dispatched": dispatched}

    async def reclaim_expired_leases(self) -> int:
        now = utcnow()
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            service = TaskService(session)
            expired = await repo.list_expired_dispatched(now)
            count = 0
            for task in expired:
                await service.requeue_expired(task)
                count += 1
                logger.warning("任务 %s 分发租约过期，已重新入队", task.task_id)
            if count:
                await session.commit()
            return count

    async def timeout_running_tasks(self) -> int:
        now = utcnow()
        cancel_targets: list[tuple[str, str]] = []
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            service = TaskService(session)
            running_tasks = await repo.list_running()
            count = 0
            for task in running_tasks:
                if task.started_at is None:
                    continue
                deadline = ensure_utc(task.started_at) + timedelta(seconds=task.timeout_seconds)
                if deadline <= now:
                    agent_id = task.agent_id
                    await service.complete(
                        task,
                        succeeded=False,
                        error=f"task execution timed out after {task.timeout_seconds}s",
                    )
                    count += 1
                    logger.warning(
                        "任务 %s 执行超时（%ds）-> status=%s",
                        task.task_id,
                        task.timeout_seconds,
                        task.status,
                    )
                    if agent_id:
                        cancel_targets.append((agent_id, task.task_id))
            if count:
                await session.commit()

        for agent_id, task_id in cancel_targets:
            await self._ws_manager.send_json(
                agent_id, make_message("task_cancel", {"task_id": task_id})
            )
        return count

    def _pick_agent(self, online_agent_ids: list[str]) -> str:
        chosen = online_agent_ids[self._rr_cursor % len(online_agent_ids)]
        self._rr_cursor += 1
        return chosen

    async def dispatch_queued_tasks(self) -> int:
        online_agent_ids = self._ws_manager.online_agent_ids()
        if not online_agent_ids:
            return 0

        now = utcnow()
        lease_expires_at = now + timedelta(seconds=self._lease_seconds)
        to_send: list[tuple[str, dict]] = []
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            candidates = await repo.list_dispatchable(now, online_agent_ids)
            for task in candidates:
                target_agent_id = task.agent_id or self._pick_agent(online_agent_ids)
                if target_agent_id not in online_agent_ids:
                    continue
                claimed = await repo.claim_for_dispatch(
                    task_id=task.task_id,
                    agent_id=target_agent_id,
                    dispatched_at=now,
                    lease_expires_at=lease_expires_at,
                )
                if not claimed:
                    continue
                to_send.append(
                    (
                        target_agent_id,
                        make_message(
                            "task_dispatch",
                            {
                                "task_id": task.task_id,
                                "type": task.type,
                                "payload": task.payload,
                                "timeout_seconds": task.timeout_seconds,
                            },
                        ),
                    )
                )
            if to_send:
                await session.commit()

        dispatched = 0
        failed_task_ids: list[str] = []
        for agent_id, message in to_send:
            sent = await self._ws_manager.send_json(agent_id, message)
            if sent:
                dispatched += 1
                logger.info("已下发任务 %s 至 Agent %s", message["data"]["task_id"], agent_id)
            else:
                failed_task_ids.append(message["data"]["task_id"])

        if failed_task_ids:
            async with self._session_factory() as session:
                repo = TaskRepository(session)
                service = TaskService(session)
                for task_id in failed_task_ids:
                    task = await repo.get_by_task_id(task_id)
                    if task is not None and task.status == "dispatched":
                        await service.requeue_expired(task)
                        logger.warning("任务 %s 下发失败（Agent 已断线），立即重新入队", task_id)
                await session.commit()

        return dispatched
