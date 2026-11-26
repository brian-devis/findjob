"""安全相关：密码哈希、JWT、Agent 凭据生成。

- 密码：argon2id（argon2-cffi）。
- JWT：HS256，access（短）+ refresh（长，含 ver 用于吊销）。
- Agent 凭据：256 位随机，base64url；仅存哈希。
"""
import base64
import secrets
import uuid
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from app.core.config import get_settings
from app.core.time import utcnow

_password_hasher = PasswordHasher()

TOKEN_ACCESS = "access"
TOKEN_REFRESH = "refresh"


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerificationError:
        return False


def generate_agent_secret() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def generate_uuid() -> str:
    return str(uuid.uuid4())


def _encode_token(subject: str, token_type: str, version: int, expires: timedelta, jti: str | None = None) -> str:
    settings = get_settings()
    now = utcnow()
    payload = {
        "sub": subject,
        "type": token_type,
        "ver": version,
        "iat": now,
        "exp": now + expires,
    }
    if jti is not None:
        payload["jti"] = jti
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(admin_id: str, username: str, token_version: int) -> str:
    settings = get_settings()
    return _encode_token(
        subject=f"{admin_id}:{username}",
        token_type=TOKEN_ACCESS,
        version=token_version,
        expires=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(admin_id: str, username: str, token_version: int) -> str:
    settings = get_settings()
    return _encode_token(
        subject=f"{admin_id}:{username}",
        token_type=TOKEN_REFRESH,
        version=token_version,
        expires=timedelta(days=settings.refresh_token_expire_days),
        jti=generate_uuid(),
    )


def decode_token(token: str, expected_type: str) -> dict:
    settings = get_settings()
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("token type mismatch")
    return payload
