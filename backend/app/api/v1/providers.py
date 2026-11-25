"""AI Provider 管理接口（仅返回 API Key 掩码，不回显明文）。"""
from fastapi import APIRouter, Query

from app.api.deps import CSRFRequired, CurrentAdmin, DBSession
from app.models.ai_provider import AIProvider
from app.schemas.common import ok
from app.schemas.provider import ProviderCreate, ProviderOut, ProviderUpdate
from app.services.provider_service import ProviderService

router = APIRouter()


def _serialize_provider(provider: AIProvider) -> dict:
    data = ProviderOut.model_validate(provider).model_dump()
    data["api_key_masked"] = ProviderService.get_masked_api_key(provider)
    return data


@router.post("")
async def create_provider(
    body: ProviderCreate, session: DBSession, _: CSRFRequired, admin: CurrentAdmin
) -> dict:
    provider = await ProviderService(session).create(
        name=body.name.strip(),
        base_url=body.base_url,
        api_format=body.api_format,
        model=body.model.strip(),
        api_key=body.api_key,
        enabled=body.enabled,
    )
    await session.commit()
    return ok(_serialize_provider(provider))


@router.get("")
async def list_providers(
    session: DBSession,
    admin: CurrentAdmin,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    service = ProviderService(session)
    items = await service.list(offset=offset, limit=limit)
    total = await service.count()
    return ok({"items": [_serialize_provider(p) for p in items], "total": total})


@router.get("/{provider_id}")
async def get_provider(provider_id: int, session: DBSession, admin: CurrentAdmin) -> dict:
    provider = await ProviderService(session).get(provider_id)
    return ok(_serialize_provider(provider))


@router.patch("/{provider_id}")
async def update_provider(
    provider_id: int,
    body: ProviderUpdate,
    session: DBSession,
    _: CSRFRequired,
    admin: CurrentAdmin,
) -> dict:
    provider = await ProviderService(session).update(
        provider_id,
        name=body.name.strip() if body.name is not None else None,
        base_url=body.base_url,
        api_format=body.api_format,
        model=body.model.strip() if body.model is not None else None,
        api_key=body.api_key,
        enabled=body.enabled,
    )
    await session.commit()
    return ok(_serialize_provider(provider))


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: int, session: DBSession, _: CSRFRequired, admin: CurrentAdmin
) -> dict:
    await ProviderService(session).delete(provider_id)
    await session.commit()
    return ok()
