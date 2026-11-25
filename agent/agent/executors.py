"""内置任务执行器：PING / SYSTEM_INFO（支持超时与取消）。"""
import asyncio
import os
import platform
import shutil
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

ExecutorFunc = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class UnsupportedTaskTypeError(ValueError):
    """收到未注册的任务类型。"""


async def execute_ping(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "pong": True,
        "echo": payload,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def execute_system_info(payload: dict[str, Any]) -> dict[str, Any]:
    disk = shutil.disk_usage(os.getcwd())
    return {
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count() or 1,
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "timestamp": datetime.now(UTC).isoformat(),
    }


class TaskExecutorRegistry:
    def __init__(self) -> None:
        self._executors: dict[str, ExecutorFunc] = {
            "PING": execute_ping,
            "SYSTEM_INFO": execute_system_info,
        }

    def register(self, task_type: str, func: ExecutorFunc) -> None:
        self._executors[task_type] = func

    async def execute(
        self,
        task_type: str,
        payload: dict[str, Any],
        timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        func = self._executors.get(task_type)
        if func is None:
            raise UnsupportedTaskTypeError(f"unsupported task type: {task_type}")
        return await asyncio.wait_for(func(payload), timeout=timeout_seconds)
