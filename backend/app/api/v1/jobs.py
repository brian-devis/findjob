"""求职偏好、BOSS 岗位扫描、AI 匹配与投递漏斗接口。"""
from fastapi import APIRouter, Query, Request

from app.api.deps import CSRFRequired, CurrentAdmin, DBSession
from app.schemas.common import ok
from app.schemas.job import (
    BossJobApplyRequest,
    BossJobAutoApplyRequest,
    BossJobBatchScoreRequest,
    BossJobImportRequest,
    BossJobOut,
    BossJobScanRequest,
    BossJobScoreRequest,
    JobPreferenceOut,
    JobPreferenceUpdate,
)
from app.schemas.task import TaskOut
from app.services.audit_service import AuditService
from app.services.job_service import JobService

router = APIRouter()


@router.get("/preferences")
async def get_preferences(session: DBSession, admin: CurrentAdmin) -> dict:
    service = JobService(session)
    pref = await service.get_preference()
    await session.commit()
    return ok(JobPreferenceOut.model_validate(pref).model_dump())


@router.put("/preferences")
async def update_preferences(
    body: JobPreferenceUpdate,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    pref = await JobService(session).update_preference(**body.model_dump())
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="job.preference_update",
        target=str(pref.id),
        detail={
            "auto_apply_enabled": pref.auto_apply_enabled,
            "auto_apply_min_score": pref.auto_apply_min_score,
            "daily_apply_limit": pref.daily_apply_limit,
        },
    )
    await session.commit()
    return ok(JobPreferenceOut.model_validate(pref).model_dump())


@router.get("")
async def list_jobs(
    session: DBSession,
    admin: CurrentAdmin,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
    min_score: int | None = Query(default=None, ge=0, le=100),
) -> dict:
    res = await JobService(session).list_jobs(
        offset=offset, limit=limit, status=status, min_score=min_score
    )
    await session.commit()
    return ok(
        {
            "items": [BossJobOut.model_validate(j).model_dump() for j in res["items"]],
            "total": res["total"],
            "applied_today": res["applied_today"],
            "daily_apply_limit": res["daily_apply_limit"],
            "auto_apply_enabled": res["auto_apply_enabled"],
            "auto_apply_min_score": res["auto_apply_min_score"],
            "stats": res["stats"],
        }
    )


@router.post("/import")
async def import_jobs(
    body: BossJobImportRequest,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    res = await JobService(session).ingest_jobs([item.model_dump() for item in body.items])
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="job.import",
        target="boss_jobs",
        detail={
            "created": res["created"],
            "updated": res["updated"],
            "skipped": res["skipped"],
        },
    )
    await session.commit()
    return ok(
        {
            "created": res["created"],
            "updated": res["updated"],
            "skipped": res["skipped"],
            "items": [BossJobOut.model_validate(j).model_dump() for j in res["items"]],
        }
    )


@router.post("/scan")
async def scan_jobs(
    request: Request,
    body: BossJobScanRequest,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    task = await JobService(session).dispatch_scan_task(
        agent_id=body.agent_id,
        keywords=body.keywords,
        city=body.city,
        max_jobs=body.max_jobs,
        dry_run=body.dry_run,
        timeout_seconds=body.timeout_seconds,
    )
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="job.scan",
        target=task.task_id,
        detail={"agent_id": task.agent_id, "keywords": task.payload.get("keywords")},
    )
    await session.commit()
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.trigger()
    return ok(TaskOut.model_validate(task).model_dump())


@router.post("/ai-score-batch")
async def ai_score_jobs_batch(
    body: BossJobBatchScoreRequest,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    res = await JobService(session).score_jobs_batch(
        limit=body.limit, provider_id=body.provider_id, resume_id=body.resume_id
    )
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="job.ai_score_batch",
        target="boss_jobs",
        detail={"scored": res["scored"], "failed": res["failed"]},
    )
    await session.commit()
    return ok(
        {
            "scored": res["scored"],
            "failed": res["failed"],
            "items": [BossJobOut.model_validate(j).model_dump() for j in res["items"]],
            "errors": res["errors"],
        }
    )


@router.post("/{job_id}/ai-score")
async def ai_score_job(
    job_id: int,
    body: BossJobScoreRequest,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    job = await JobService(session).score_job_with_ai(
        job_id, provider_id=body.provider_id, resume_id=body.resume_id
    )
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="job.ai_score",
        target=str(job.id),
        detail={"match_score": job.match_score, "boss_job_id": job.boss_job_id},
    )
    await session.commit()
    return ok(BossJobOut.model_validate(job).model_dump())


@router.post("/{job_id}/apply")
async def apply_job(
    request: Request,
    job_id: int,
    body: BossJobApplyRequest,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    res = await JobService(session).dispatch_apply_task(
        job_id,
        agent_id=body.agent_id,
        greeting=body.greeting,
        dry_run=body.dry_run,
        timeout_seconds=body.timeout_seconds,
        is_auto=False,
    )
    job = res["job"]
    task = res["task"]
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="job.apply",
        target=str(job.id),
        detail={"task_id": task.task_id, "dry_run": body.dry_run, "title": job.title},
    )
    await session.commit()
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.trigger()
    return ok(
        {
            "job": BossJobOut.model_validate(job).model_dump(),
            "task": TaskOut.model_validate(task).model_dump(),
        }
    )


@router.post("/{job_id}/skip")
async def skip_job(
    job_id: int,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    job = await JobService(session).skip_job(job_id)
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="job.skip",
        target=str(job.id),
        detail={"boss_job_id": job.boss_job_id},
    )
    await session.commit()
    return ok(BossJobOut.model_validate(job).model_dump())


@router.post("/{job_id}/restore")
async def restore_job(
    job_id: int,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    job = await JobService(session).restore_job(job_id)
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="job.restore",
        target=str(job.id),
        detail={"boss_job_id": job.boss_job_id, "status": job.status},
    )
    await session.commit()
    return ok(BossJobOut.model_validate(job).model_dump())


@router.post("/auto-apply")
async def auto_apply_jobs(
    request: Request,
    body: BossJobAutoApplyRequest,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    res = await JobService(session).dispatch_auto_apply_batch(
        agent_id=body.agent_id,
        dry_run=body.dry_run,
        max_count=body.max_count,
    )
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="job.auto_apply",
        target="boss_jobs",
        detail={
            "dispatched_count": res["dispatched_count"],
            "dry_run": res["dry_run"],
            "min_score": res["min_score"],
        },
    )
    await session.commit()
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None and res["dispatched_count"] > 0:
        scheduler.trigger()
    return ok(res)
