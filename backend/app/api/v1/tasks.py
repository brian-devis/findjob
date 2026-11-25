"""任务接口。"""
from fastapi import APIRouter, Query, Request

from app.api.deps import CSRFRequired, CurrentAdmin, DBSession
from app.core.enums import TaskStatus
from app.schemas.common import ok
from app.schemas.task import TaskCreate, TaskOut, TaskStatusOut
from app.services.task_service import TaskService
from app.ws import make_message, ws_manager

router = APIRouter()


@router.post("")
async def create_task(
    request: Request,
    body: TaskCreate,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    service = TaskService(session)
    task = await service.create(
        type_=body.type,
        agent_id=body.agent_id,
        payload=body.payload,
        priority=body.priority,
        max_attempts=body.max_attempts,
        timeout_seconds=body.timeout_seconds,
        idempotency_key=body.idempotency_key,
        scheduled_at=body.scheduled_at,
    )
    await session.commit()
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.trigger()
    return ok(TaskOut.model_validate(task).model_dump())


@router.get("")
async def list_tasks(
    session: DBSession,
    admin: CurrentAdmin,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
) -> dict:
    service = TaskService(session)
    tasks = await service.list(offset=offset, limit=limit, status=status)
    total = await service.count(status=status)
    return ok(
        {"items": [TaskOut.model_validate(t).model_dump() for t in tasks], "total": total}
    )


@router.get("/{task_id}")
async def get_task(task_id: str, session: DBSession, admin: CurrentAdmin) -> dict:
    task = await TaskService(session).get(task_id)
    return ok(TaskOut.model_validate(task).model_dump())


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str, session: DBSession, _: CSRFRequired, admin: CurrentAdmin
) -> dict:
    service = TaskService(session)
    task = await service.get(task_id)
    prev_status = task.status_enum
    target_agent_id = task.agent_id
    task = await service.cancel(task)
    await session.commit()
    if target_agent_id and prev_status in (TaskStatus.DISPATCHED, TaskStatus.RUNNING):
        await ws_manager.send_json(
            target_agent_id, make_message("task_cancel", {"task_id": task.task_id})
        )
    return ok(
        TaskStatusOut(task_id=task.task_id, status=task.status_enum, attempt=task.attempt).model_dump()
    )
