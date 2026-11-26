"""AI Provider API Key 加密与脱敏工具（AES-256-GCM）。

设计（见 docs/security.md 与 docs/database.md）：
- Agent secret 用于认证 -> argon2id 不可逆哈希；
- AI Provider API Key 用于调用上游 -> AES-256-GCM 可逆加密存储，绝不回显明文。
"""
import base64
import binascii
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings

_PREFIX = "v1:"
_NONCE_SIZE = 12
_HKDF_INFO = b"aijob-provider-api-key-aes-gcm-v1"
_HKDF_SALT = b"aijob-static-kdf-salt-v1"


def _derive_aes_key() -> bytes:
    settings = get_settings()
    raw = (settings.provider_master_key or settings.jwt_secret).strip()
    if len(raw) < 16:
        raise ValueError("加密主密钥未配置或过短")
    raw_secret = raw.encode("utf-8")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    )
    return hkdf.derive(raw_secret)


def encrypt_secret(plaintext: str) -> str:
    """使用 AES-256-GCM 加密明文并返回带版本前缀的密文字符串。"""
    key = _derive_aes_key()
    nonce = secrets.token_bytes(_NONCE_SIZE)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    token = base64.urlsafe_b64encode(nonce + ct).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_secret(ciphertext: str) -> str:
    """解密由 encrypt_secret 生成的密文。"""
    if not ciphertext.startswith(_PREFIX):
        raise ValueError("不支持的密文格式")
    try:
        raw = base64.urlsafe_b64decode(ciphertext[len(_PREFIX) :].encode("ascii"))
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise ValueError("密文格式非法") from exc
    if len(raw) <= _NONCE_SIZE:
        raise ValueError("密文长度非法")
    nonce, ct = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
    key = _derive_aes_key()
    try:
        plain = AESGCM(key).decrypt(nonce, ct, None)
    except InvalidTag as exc:
        raise ValueError("密文校验失败") from exc
    return plain.decode("utf-8")


def mask_api_key(plaintext: str | None) -> str | None:
    """将 API Key 脱敏为掩码（不暴露明文）。"""
    if not plaintext:
        return None
    if len(plaintext) <= 8:
        return "****"
    return f"{plaintext[:4]}****{plaintext[-4:]}"
