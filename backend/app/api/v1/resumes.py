"""简历管理与 AI 审阅改写接口。"""
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile

from app.api.deps import CSRFRequired, CurrentAdmin, DBSession
from app.core.enums import AgentStatus, TaskType
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.schemas.common import ok
from app.schemas.resume import (
    ResumeAIRequest,
    ResumeCreate,
    ResumeOut,
    ResumeSummaryOut,
    ResumeSyncBossRequest,
    ResumeUpdate,
)
from app.schemas.task import TaskOut
from app.services.agent_service import AgentService
from app.services.audit_service import AuditService
from app.services.resume_exporter import (
    build_content_disposition,
    build_resume_docx,
    build_resume_markdown,
)
from app.services.resume_parser import MAX_RESUME_UPLOAD_BYTES, parse_resume_upload
from app.services.resume_service import ResumeService
from app.services.task_service import TaskService

logger = get_logger("app.api.resumes")
router = APIRouter()


@router.get("")
async def list_resumes(
    session: DBSession,
    admin: CurrentAdmin,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    service = ResumeService(session)
    items = await service.list(offset=offset, limit=limit)
    total = await service.count()
    return ok({"items": [ResumeSummaryOut.model_validate(r).model_dump() for r in items], "total": total})


@router.get("/{resume_id}")
async def get_resume(resume_id: int, session: DBSession, admin: CurrentAdmin) -> dict:
    resume = await ResumeService(session).get(resume_id)
    return ok(ResumeOut.model_validate(resume).model_dump())


@router.get("/{resume_id}/export")
async def export_resume(
    resume_id: int,
    session: DBSession,
    admin: CurrentAdmin,
    format: str = Query(default="docx", pattern="^(docx|md)$"),
) -> Response:
    resume = await ResumeService(session).get(resume_id)
    if format == "md":
        data = build_resume_markdown(
            title=resume.title,
            target_role=resume.target_role,
            raw_content=resume.raw_content,
        )
        media_type = "text/markdown; charset=utf-8"
    else:
        data = build_resume_docx(
            title=resume.title,
            target_role=resume.target_role,
            raw_content=resume.raw_content,
        )
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": build_content_disposition(resume.title, format)},
    )


@router.post("")
async def create_resume(
    body: ResumeCreate, session: DBSession, _: CSRFRequired, admin: CurrentAdmin
) -> dict:
    resume = await ResumeService(session).create(
        title=body.title,
        target_role=(body.target_role or "").strip() or None,
        source_filename=None,
        source_format=body.source_format.strip() or "markdown",
        raw_content=body.raw_content,
        structured_json=body.structured_json,
    )
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="resume.create",
        target=str(resume.id),
        detail={"title": resume.title, "source_format": resume.source_format},
    )
    await session.commit()
    return ok(ResumeOut.model_validate(resume).model_dump())


@router.post("/upload")
async def upload_resume(
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str | None, Form()] = None,
    target_role: Annotated[str | None, Form()] = None,
) -> dict:
    content = await file.read(MAX_RESUME_UPLOAD_BYTES + 1)
    filename = file.filename or "resume.txt"
    fmt, text = parse_resume_upload(filename, content)
    final_title = (title or "").strip() or Path(filename).stem or "上传简历"

    resume = await ResumeService(session).create(
        title=final_title[:128],
        target_role=target_role.strip() if target_role and target_role.strip() else None,
        source_filename=filename[:255],
        source_format=fmt,
        raw_content=text,
    )
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="resume.upload",
        target=str(resume.id),
        detail={"title": resume.title, "source_format": fmt, "source_filename": filename},
    )
    await session.commit()
    return ok(ResumeOut.model_validate(resume).model_dump())


@router.patch("/{resume_id}")
async def update_resume(
    resume_id: int,
    body: ResumeUpdate,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    resume = await ResumeService(session).update(
        resume_id,
        title=body.title,
        target_role=body.target_role,
        raw_content=body.raw_content,
        structured_json=body.structured_json,
    )
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="resume.update",
        target=str(resume.id),
        detail={"title": resume.title},
    )
    await session.commit()
    return ok(ResumeOut.model_validate(resume).model_dump())


@router.post("/{resume_id}/activate")
async def activate_resume(
    resume_id: int, session: DBSession, _: CSRFRequired, admin: CurrentAdmin
) -> dict:
    resume = await ResumeService(session).activate(resume_id)
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="resume.activate",
        target=str(resume.id),
        detail={"title": resume.title},
    )
    await session.commit()
    return ok(ResumeOut.model_validate(resume).model_dump())


@router.delete("/{resume_id}")
async def delete_resume(
    resume_id: int, session: DBSession, _: CSRFRequired, admin: CurrentAdmin
) -> dict:
    await ResumeService(session).delete(resume_id)
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="resume.delete",
        target=str(resume_id),
    )
    await session.commit()
    return ok()


@router.post("/{resume_id}/ai-review")
async def ai_review_resume(
    resume_id: int,
    body: ResumeAIRequest,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    resume = await ResumeService(session).review_with_ai(
        resume_id, provider_id=body.provider_id, target_role=body.target_role
    )
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="resume.ai_review",
        target=str(resume.id),
        detail={"score": (resume.ai_review_json or {}).get("score")},
    )
    await session.commit()
    return ok(ResumeOut.model_validate(resume).model_dump())


@router.post("/{resume_id}/ai-rewrite")
async def ai_rewrite_resume(
    resume_id: int,
    body: ResumeAIRequest,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    new_resume = await ResumeService(session).rewrite_with_ai(
        resume_id,
        provider_id=body.provider_id,
        target_role=body.target_role,
        instruction=body.instruction,
    )
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="resume.ai_rewrite",
        target=str(new_resume.id),
        detail={"parent_id": resume_id, "title": new_resume.title},
    )
    await session.commit()
    return ok(ResumeOut.model_validate(new_resume).model_dump())


@router.post("/{resume_id}/sync-boss")
async def sync_resume_to_boss(
    request: Request,
    resume_id: int,
    body: ResumeSyncBossRequest,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    resume = await ResumeService(session).get(resume_id)
    target_agent_id: str | None = (body.agent_id or "").strip() or None
    if target_agent_id:
        agent = await AgentService(session).get(target_agent_id)
        if agent.status != AgentStatus.ACTIVE.value:
            raise ValidationError("目标 Agent 已被吊销，无法下发同步任务")
        target_agent_id = agent.agent_id

    task = await TaskService(session).create(
        type_=TaskType.BOSS_SYNC_RESUME,
        agent_id=target_agent_id,
        payload={
            "resume_id": resume.id,
            "title": resume.title,
            "target_role": resume.target_role,
            "raw_content": resume.raw_content,
            "structured_json": resume.structured_json or {},
            "dry_run": body.dry_run,
        },
        priority=10,
        max_attempts=1,
        timeout_seconds=body.timeout_seconds,
    )
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="resume.sync_boss",
        target=str(resume.id),
        detail={
            "task_id": task.task_id,
            "agent_id": task.agent_id,
            "dry_run": body.dry_run,
        },
    )
    await session.commit()
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        try:
            scheduler.trigger()
        except Exception as exc:  # noqa: BLE001
            logger.warning("唤醒任务调度器失败，等待下次轮询: %s", exc)
    return ok(TaskOut.model_validate(task).model_dump())
