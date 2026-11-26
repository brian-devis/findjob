"""审计日志查询接口。"""
from fastapi import APIRouter, Query

from app.api.deps import CurrentAdmin, DBSession
from app.schemas.audit import AuditLogOut
from app.schemas.common import ok
from app.services.audit_service import AuditService

router = APIRouter()


@router.get("")
async def list_audit_logs(
    session: DBSession,
    admin: CurrentAdmin,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None),
    actor: str | None = Query(default=None),
) -> dict:
    service = AuditService(session)
    items = await service.list(offset=offset, limit=limit, action=action, actor=actor)
    total = await service.count(action=action, actor=actor)
    return ok(
        {"items": [AuditLogOut.model_validate(x).model_dump() for x in items], "total": total}
    )
