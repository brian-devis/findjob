"""任务调度循环测试：分发、租约过期回收、执行超时、失败回滚。"""
from datetime import timedelta

import pytest

from app.core.enums import TaskStatus, TaskType
from app.core.time import utcnow
from app.services.agent_service import AgentService
from app.services.scheduler import TaskScheduler
from app.services.task_service import TaskService
from app.ws.manager import AgentConnectionManager


class FakeWebSocket:
    def __init__(self, *, fail_send: bool = False) -> None:
        self.sent: list[dict] = []
        self.closed: list[tuple[int, str]] = []
        self.fail_send = fail_send

    async def send_json(self, data: dict) -> None:
        if self.fail_send:
            raise RuntimeError("broken pipe")
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed.append((code, reason))


@pytest.mark.asyncio
async def test_scheduler_dispatch_priority_and_round_robin(session_factory):
    ws_manager = AgentConnectionManager()
    async with session_factory() as s:
        agent1, _ = await AgentService(s).register("agent-1")
        agent2, _ = await AgentService(s).register("agent-2")
        task_svc = TaskService(s)
        t_low = await task_svc.create(
            type_=TaskType.PING,
            agent_id=None,
            payload={"k": "low"},
            priority=1,
            max_attempts=1,
            timeout_seconds=60,
        )
        t_high = await task_svc.create(
            type_=TaskType.SYSTEM_INFO,
            agent_id=None,
            payload={"k": "high"},
            priority=10,
            max_attempts=1,
            timeout_seconds=60,
        )
        t_future = await task_svc.create(
            type_=TaskType.PING,
            agent_id=agent1.agent_id,
            payload={},
            priority=99,
            max_attempts=1,
            timeout_seconds=60,
            scheduled_at=utcnow() + timedelta(hours=1),
        )
        await s.commit()

    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket()
    await ws_manager.connect(agent1.agent_id, ws1)  # type: ignore[arg-type]
    await ws_manager.connect(agent2.agent_id, ws2)  # type: ignore[arg-type]

    scheduler = TaskScheduler(
        session_factory=session_factory,
        ws_manager=ws_manager,
        dispatch_lease_seconds=30,
    )
    stats = await scheduler.run_once()
    assert stats == {"requeued": 0, "timed_out": 0, "dispatched": 2}

    # 高优先级先分发给 agent1，低优先级轮询分发给 agent2
    assert len(ws1.sent) == 1
    assert ws1.sent[0]["type"] == "task_dispatch"
    assert ws1.sent[0]["data"]["task_id"] == t_high.task_id
    assert len(ws2.sent) == 1
    assert ws2.sent[0]["data"]["task_id"] == t_low.task_id

    # 延迟任务未到时间，保持 queued
    async with session_factory() as s:
        future_task = await TaskService(s).get(t_future.task_id)
        assert future_task.status == TaskStatus.QUEUED.value


@pytest.mark.asyncio
async def test_scheduler_requeue_on_send_failure(session_factory):
    ws_manager = AgentConnectionManager()
    async with session_factory() as s:
        agent, _ = await AgentService(s).register("flaky-agent")
        task = await TaskService(s).create(
            type_=TaskType.PING,
            agent_id=agent.agent_id,
            payload={},
            priority=0,
            max_attempts=1,
            timeout_seconds=60,
        )
        await s.commit()

    broken_ws = FakeWebSocket(fail_send=True)
    await ws_manager.connect(agent.agent_id, broken_ws)  # type: ignore[arg-type]

    scheduler = TaskScheduler(session_factory=session_factory, ws_manager=ws_manager)
    stats = await scheduler.run_once()
    assert stats["dispatched"] == 0
    assert not ws_manager.is_online(agent.agent_id)

    async with session_factory() as s:
        reloaded = await TaskService(s).get(task.task_id)
        assert reloaded.status == TaskStatus.QUEUED.value
        assert reloaded.lease_expires_at is None


@pytest.mark.asyncio
async def test_scheduler_reclaim_expired_lease(session_factory):
    ws_manager = AgentConnectionManager()
    async with session_factory() as s:
        agent, _ = await AgentService(s).register("offline-agent")
        svc = TaskService(s)
        task = await svc.create(
            type_=TaskType.PING,
            agent_id=agent.agent_id,
            payload={},
            priority=0,
            max_attempts=1,
            timeout_seconds=60,
        )
        await svc.dispatch(task, lease_seconds=10)
        task.lease_expires_at = utcnow() - timedelta(seconds=5)
        await s.commit()

    scheduler = TaskScheduler(session_factory=session_factory, ws_manager=ws_manager)
    stats = await scheduler.run_once()
    assert stats["requeued"] == 1

    async with session_factory() as s:
        reloaded = await TaskService(s).get(task.task_id)
        assert reloaded.status == TaskStatus.QUEUED.value
        assert reloaded.dispatched_at is None


@pytest.mark.asyncio
async def test_scheduler_timeout_running_tasks_retry_and_fail(session_factory):
    ws_manager = AgentConnectionManager()
    async with session_factory() as s:
        agent, _ = await AgentService(s).register("slow-agent")
        svc = TaskService(s)

        # 任务 1：max_attempts=1，超时直接进入 failed
        t_fail = await svc.create(
            type_=TaskType.PING,
            agent_id=agent.agent_id,
            payload={},
            priority=0,
            max_attempts=1,
            timeout_seconds=5,
        )
        await svc.dispatch(t_fail, lease_seconds=30)
        await svc.ack(t_fail)
        t_fail.started_at = utcnow() - timedelta(seconds=20)

        # 任务 2：max_attempts=2，超时自动重试回 queued
        t_retry = await svc.create(
            type_=TaskType.PING,
            agent_id=agent.agent_id,
            payload={},
            priority=0,
            max_attempts=2,
            timeout_seconds=5,
        )
        await svc.dispatch(t_retry, lease_seconds=30)
        await svc.ack(t_retry)
        t_retry.started_at = utcnow() - timedelta(seconds=20)
        await s.commit()

    ws = FakeWebSocket()
    await ws_manager.connect(agent.agent_id, ws)  # type: ignore[arg-type]

    scheduler = TaskScheduler(session_factory=session_factory, ws_manager=ws_manager)
    timed_out = await scheduler.timeout_running_tasks()
    assert timed_out == 2

    # 在线 Agent 收到两次 task_cancel
    cancel_ids = {m["data"]["task_id"] for m in ws.sent if m["type"] == "task_cancel"}
    assert cancel_ids == {t_fail.task_id, t_retry.task_id}

    async with session_factory() as s:
        r_fail = await TaskService(s).get(t_fail.task_id)
        r_retry = await TaskService(s).get(t_retry.task_id)
        assert r_fail.status == TaskStatus.FAILED.value
        assert r_fail.attempt == 1
        assert "timed out" in (r_fail.error or "")
        assert r_retry.status == TaskStatus.QUEUED.value
        assert r_retry.attempt == 1
