"""AI Provider 服务：增删改查与 AES-GCM 密钥加解密。"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret, encrypt_secret, mask_api_key
from app.core.exceptions import ConflictError, NotFoundError
from app.models.ai_provider import AIProvider
from app.repositories.provider import AIProviderRepository


class ProviderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AIProviderRepository(session)

    async def create(
        self,
        *,
        name: str,
        base_url: str,
        api_format: str,
        model: str,
        api_key: str | None,
        enabled: bool = True,
    ) -> AIProvider:
        if await self._repo.get_by_name(name) is not None:
            raise ConflictError(f"Provider 名称「{name}」已存在")

        api_key_enc = encrypt_secret(api_key) if api_key else None
        return await self._repo.create(
            name=name,
            base_url=base_url,
            api_format=api_format,
            model=model,
            api_key_enc=api_key_enc,
            enabled=enabled,
        )

    async def get(self, provider_id: int) -> AIProvider:
        provider = await self._repo.get_by_id(provider_id)
        if provider is None:
            raise NotFoundError("AI Provider 不存在")
        return provider

    async def list(self, offset: int = 0, limit: int = 50) -> list[AIProvider]:
        return await self._repo.list(offset=offset, limit=limit)

    async def count(self) -> int:
        return await self._repo.count()

    async def update(
        self,
        provider_id: int,
        *,
        name: str | None = None,
        base_url: str | None = None,
        api_format: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        enabled: bool | None = None,
    ) -> AIProvider:
        provider = await self.get(provider_id)
        if name is not None and name != provider.name:
            if await self._repo.get_by_name(name) is not None:
                raise ConflictError(f"Provider 名称「{name}」已存在")
            provider.name = name
        if base_url is not None:
            provider.base_url = base_url
        if api_format is not None:
            provider.api_format = api_format
        if model is not None:
            provider.model = model
        if api_key is not None:
            provider.api_key_enc = encrypt_secret(api_key) if api_key else None
        if enabled is not None:
            provider.enabled = enabled
        await self._session.flush()
        return provider

    async def delete(self, provider_id: int) -> None:
        provider = await self.get(provider_id)
        await self._repo.delete(provider)

    @staticmethod
    def get_decrypted_api_key(provider: AIProvider) -> str | None:
        if not provider.api_key_enc:
            return None
        return decrypt_secret(provider.api_key_enc)

    @staticmethod
    def get_masked_api_key(provider: AIProvider) -> str | None:
        if not provider.api_key_enc:
            return None
        try:
            plain = decrypt_secret(provider.api_key_enc)
        except ValueError:
            return "****"
        return mask_api_key(plain)
