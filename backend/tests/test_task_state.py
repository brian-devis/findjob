"""任务状态机单元测试。"""
import pytest

from app.core.enums import TaskType
from app.core.exceptions import InvalidStateError
from app.services.task_service import TaskService


async def _create(service: TaskService, max_attempts: int = 1):
    return await service.create(
        type_=TaskType.PING,
        agent_id=None,
        payload={},
        priority=0,
        max_attempts=max_attempts,
        timeout_seconds=60,
    )


async def test_happy_path(session):
    service = TaskService(session)
    task = await _create(service)
    assert task.status == "queued"

    await service.dispatch(task, lease_seconds=30)
    assert task.status == "dispatched"
    assert task.lease_expires_at is not None

    await service.ack(task)
    assert task.status == "running"
    assert task.lease_expires_at is None

    await service.complete(task, succeeded=True, result={"ok": True})
    assert task.status == "succeeded"
    assert task.result == {"ok": True}


async def test_illegal_transition(session):
    service = TaskService(session)
    task = await _create(service)
    with pytest.raises(InvalidStateError):
        await service.complete(task, succeeded=True)  # queued -> succeeded 非法


async def test_cancel_from_queued(session):
    service = TaskService(session)
    task = await _create(service)
    await service.cancel(task)
    assert task.status == "cancelled"


async def test_requeue_expired(session):
    service = TaskService(session)
    task = await _create(service)
    await service.dispatch(task, lease_seconds=30)
    await service.requeue_expired(task)
    assert task.status == "queued"
    assert task.lease_expires_at is None


async def test_retry_then_terminal_fail(session):
    service = TaskService(session)
    task = await _create(service, max_attempts=3)

    for expected_attempt in (1, 2, 3):
        await service.dispatch(task, lease_seconds=30)
        await service.ack(task)
        await service.complete(task, succeeded=False, error="boom")
        assert task.attempt == expected_attempt

    # 第三次失败后达到 max_attempts，进入终态 failed
    assert task.status == "failed"


async def test_complete_success_clears_error(session):
    service = TaskService(session)
    task = await _create(service)
    await service.dispatch(task, lease_seconds=30)
    await service.ack(task)
    await service.complete(task, succeeded=True)
    assert task.error is None
    assert task.finished_at is not None
