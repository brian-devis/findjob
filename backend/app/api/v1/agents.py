"""Agent 管理接口。"""
from fastapi import APIRouter, Query

from app.api.deps import CSRFRequired, CurrentAdmin, DBSession
from app.schemas.agent import AgentCreate, AgentOut, AgentSecretOut
from app.schemas.common import ok
from app.services.agent_service import AgentService
from app.services.audit_service import AuditService
from app.ws import WS_CLOSE_AGENT_REVOKED, WS_CLOSE_AUTH_FAILED, ws_manager

router = APIRouter()


def _serialize_agent(agent) -> dict:
    data = AgentOut.model_validate(agent).model_dump()
    data["online"] = ws_manager.is_online(agent.agent_id)
    return data


@router.post("")
async def register(
    body: AgentCreate, session: DBSession, _: CSRFRequired, admin: CurrentAdmin
) -> dict:
    agent, secret = await AgentService(session).register(body.name)
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="agent.register",
        target=agent.agent_id,
        detail={"name": agent.name},
    )
    await session.commit()
    return ok(AgentSecretOut(agent_id=agent.agent_id, secret=secret).model_dump())


@router.get("")
async def list_agents(
    session: DBSession,
    admin: CurrentAdmin,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    service = AgentService(session)
    agents = await service.list(offset=offset, limit=limit)
    total = await service.count()
    return ok(
        {"items": [_serialize_agent(a) for a in agents], "total": total}
    )


@router.get("/{agent_id}")
async def get_agent(agent_id: str, session: DBSession, admin: CurrentAdmin) -> dict:
    agent = await AgentService(session).get(agent_id)
    return ok(_serialize_agent(agent))


@router.post("/{agent_id}/rotate-secret")
async def rotate_secret(
    agent_id: str, session: DBSession, _: CSRFRequired, admin: CurrentAdmin
) -> dict:
    agent, secret = await AgentService(session).rotate_secret(agent_id)
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="agent.rotate_secret",
        target=agent.agent_id,
        detail={"secret_version": agent.secret_version},
    )
    await session.commit()
    await ws_manager.disconnect_agent(
        agent_id, code=WS_CLOSE_AUTH_FAILED, reason="agent secret rotated"
    )
    return ok(AgentSecretOut(agent_id=agent.agent_id, secret=secret).model_dump())


@router.post("/{agent_id}/revoke")
async def revoke_agent(
    agent_id: str, session: DBSession, _: CSRFRequired, admin: CurrentAdmin
) -> dict:
    agent = await AgentService(session).revoke(agent_id)
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="agent.revoke",
        target=agent.agent_id,
        detail={"name": agent.name},
    )
    await session.commit()
    await ws_manager.disconnect_agent(
        agent_id, code=WS_CLOSE_AGENT_REVOKED, reason="agent revoked"
    )
    return ok(_serialize_agent(agent))


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str, session: DBSession, _: CSRFRequired, admin: CurrentAdmin
) -> dict:
    await AgentService(session).delete(agent_id)
    await AuditService(session).record(
        actor=f"admin:{admin.username}",
        action="agent.delete",
        target=agent_id,
    )
    await session.commit()
    await ws_manager.disconnect_agent(
        agent_id, code=WS_CLOSE_AGENT_REVOKED, reason="agent deleted"
    )
    return ok()
