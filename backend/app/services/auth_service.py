"""认证服务：登录、签发/校验 token、注销。"""
import secrets as _secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import (
    TOKEN_ACCESS,
    TOKEN_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.admin import Admin
from app.repositories.admin import AdminRepository


def _extract_admin_id(payload: dict) -> int:
    """从 token payload 解析 admin_id；格式非法时抛 ValueError。"""
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise TypeError("token 缺少 sub")
    admin_id, _, _ = sub.partition(":")
    return int(admin_id)


class AuthService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = AdminRepository(session)

    async def authenticate(self, username: str, password: str) -> Admin:
        admin = await self._repo.get_by_username(username)
        if admin is None or not verify_password(password, admin.password_hash):
            raise UnauthorizedError("用户名或密码错误")
        return admin

    def issue_tokens(self, admin: Admin) -> tuple[str, str]:
        access = create_access_token(str(admin.id), admin.username, admin.token_version)
        refresh = create_refresh_token(str(admin.id), admin.username, admin.token_version)
        return access, refresh

    def generate_csrf_token(self) -> str:
        return _secrets.token_urlsafe(32)

    async def refresh_access(self, refresh_token: str) -> tuple[Admin, str]:
        try:
            payload = decode_token(refresh_token, TOKEN_REFRESH)
            admin_id = _extract_admin_id(payload)
        except Exception as exc:
            raise UnauthorizedError("refresh token 无效") from exc
        admin = await self._repo.get_by_id(admin_id)
        if admin is None or admin.token_version != payload.get("ver"):
            raise UnauthorizedError("refresh token 已失效")
        access = create_access_token(str(admin.id), admin.username, admin.token_version)
        return admin, access

    async def revoke_all(self, admin: Admin) -> None:
        admin.token_version += 1
        await self._session.flush()

    async def load_admin_from_access(self, access_token: str) -> Admin:
        try:
            payload = decode_token(access_token, TOKEN_ACCESS)
            admin_id = _extract_admin_id(payload)
        except Exception as exc:
            raise UnauthorizedError("access token 无效") from exc
        admin = await self._repo.get_by_id(admin_id)
        if admin is None or admin.token_version != payload.get("ver"):
            raise UnauthorizedError("access token 已失效")
        return admin
