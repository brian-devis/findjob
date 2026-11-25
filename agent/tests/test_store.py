"""本地 SQLite 去重存储测试。"""
from agent.store import TaskExecutionStore


def test_store_persist_and_unreported_queue(tmp_path):
    db_path = tmp_path / "nested" / "state.db"
    store = TaskExecutionStore(db_path)

    assert store.get("t1") is None
    rec = store.save_result(
        task_id="t1",
        status="succeeded",
        result={"pong": True},
        reported=False,
    )
    assert rec.task_id == "t1"
    assert rec.reported is False

    unreported = store.list_unreported()
    assert [r.task_id for r in unreported] == ["t1"]

    store.close()

    # 重新打开模拟进程重启，数据完整保留
    reopened = TaskExecutionStore(db_path)
    loaded = reopened.get("t1")
    assert loaded is not None
    assert loaded.status == "succeeded"
    assert loaded.result == {"pong": True}
    assert loaded.reported is False

    reopened.mark_reported("t1")
    assert reopened.list_unreported() == []
    loaded_after = reopened.get("t1")
    assert loaded_after is not None and loaded_after.reported is True
    reopened.close()
