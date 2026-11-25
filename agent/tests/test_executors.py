"""内置执行器测试。"""
import asyncio

import pytest

from agent.executors import TaskExecutorRegistry, UnsupportedTaskTypeError


@pytest.mark.asyncio
async def test_ping_and_system_info_executors():
    registry = TaskExecutorRegistry()

    ping_res = await registry.execute("PING", {"msg": "hello"})
    assert ping_res["pong"] is True
    assert ping_res["echo"] == {"msg": "hello"}
    assert "timestamp" in ping_res

    sys_res = await registry.execute("SYSTEM_INFO", {})
    assert sys_res["hostname"]
    assert sys_res["os"]
    assert sys_res["cpu_count"] >= 1
    assert sys_res["disk_total_bytes"] > 0


@pytest.mark.asyncio
async def test_executor_unknown_timeout_and_cancel():
    registry = TaskExecutorRegistry()

    with pytest.raises(UnsupportedTaskTypeError):
        await registry.execute("UNKNOWN_JOB", {})

    async def slow_job(payload):
        await asyncio.sleep(5)
        return {"ok": True}

    registry.register("SLOW", slow_job)

    with pytest.raises(TimeoutError):
        await registry.execute("SLOW", {}, timeout_seconds=0.05)  # type: ignore[arg-type]

    task = asyncio.create_task(registry.execute("SLOW", {}, timeout_seconds=5))
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
