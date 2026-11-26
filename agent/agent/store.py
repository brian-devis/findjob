"""本地持久化 task_id 执行记录（SQLite WAL）。

保障「至少一次投递 + task_id 幂等 = 效果上恰好一次」：
- 已完成的任务记录落盘，收到重复 task_dispatch 时不重复执行，直接重发已有结果；
- 断线期间完成或未能送达的结果标记为 reported=0，重连鉴权成功后自动补报。
"""
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    status: str
    result: dict[str, Any] | None
    error: str | None
    reported: bool
    finished_at: str


class TaskExecutionStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS executed_tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    reported INTEGER NOT NULL DEFAULT 0,
                    finished_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_executed_tasks_reported
                ON executed_tasks (reported)
                """
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> TaskRecord:
        raw_result = row["result_json"]
        result = json.loads(raw_result) if raw_result is not None else None
        return TaskRecord(
            task_id=row["task_id"],
            status=row["status"],
            result=result,
            error=row["error"],
            reported=bool(row["reported"]),
            finished_at=row["finished_at"],
        )

    def get(self, task_id: str) -> TaskRecord | None:
        cur = self._conn.execute(
            "SELECT task_id, status, result_json, error, reported, finished_at "
            "FROM executed_tasks WHERE task_id = ?",
            (task_id,),
        )
        row = cur.fetchone()
        return self._row_to_record(row) if row is not None else None

    def save_result(
        self,
        *,
        task_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        reported: bool = False,
    ) -> TaskRecord:
        finished_at = datetime.now(UTC).isoformat()
        result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO executed_tasks
                    (task_id, status, result_json, error, reported, finished_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, status, result_json, error, int(reported), finished_at),
            )
        return TaskRecord(
            task_id=task_id,
            status=status,
            result=result,
            error=error,
            reported=reported,
            finished_at=finished_at,
        )

    def mark_reported(self, task_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE executed_tasks SET reported = 1 WHERE task_id = ?",
                (task_id,),
            )

    def list_unreported(self) -> list[TaskRecord]:
        cur = self._conn.execute(
            "SELECT task_id, status, result_json, error, reported, finished_at "
            "FROM executed_tasks WHERE reported = 0 ORDER BY finished_at ASC"
        )
        return [self._row_to_record(row) for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()
