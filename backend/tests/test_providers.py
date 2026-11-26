"""AI Provider 管理与 AES-GCM 加密测试。"""
import pytest

from app.core.crypto import decrypt_secret, encrypt_secret, mask_api_key
from app.services.provider_service import ProviderService


def test_aes_gcm_encrypt_decrypt_and_mask():
    raw = "sk-live-secret-key-9876543210"
    enc1 = encrypt_secret(raw)
    enc2 = encrypt_secret(raw)
    assert enc1.startswith("v1:")
    assert enc1 != enc2  # 随机 nonce 保证密文不重复
    assert raw not in enc1
    assert decrypt_secret(enc1) == raw
    assert decrypt_secret(enc2) == raw

    # 篡改密文或非法 base64 必须校验失败并抛出 ValueError
    tampered = enc1[:-2] + ("AA" if enc1[-2:] != "AA" else "BB")
    with pytest.raises(ValueError):
        decrypt_secret(tampered)
    with pytest.raises(ValueError):
        decrypt_secret("v1:%%%bad%%%")

    assert mask_api_key(raw) == "sk-l****3210"
    assert mask_api_key("short") == "****"
    assert mask_api_key(None) is None


@pytest.mark.asyncio
async def test_provider_crud_and_secret_masking(auth, session_factory):
    c = auth["client"]
    csrf = auth["csrf"]
    plain_key = "sk-prod-very-secret-token-abcd"

    # 缺 CSRF 拒绝
    r_no_csrf = await c.post(
        "/api/providers",
        json={
            "name": "deepseek",
            "base_url": "https://api.asgo.click:8443/v1",
            "api_format": "openai",
            "model": "deepseek-v4-pro",
            "api_key": plain_key,
        },
    )
    assert r_no_csrf.status_code == 403

    # 全空白 name 应被拒绝（422）
    r_blank = await c.post(
        "/api/providers",
        json={
            "name": "   ",
            "base_url": "https://api.asgo.click:8443/v1",
            "api_format": "openai",
            "model": "deepseek-v4-pro",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r_blank.status_code == 422

    # 创建 Provider：响应仅包含掩码，不含明文
    r_create = await c.post(
        "/api/providers",
        json={
            "name": "deepseek",
            "base_url": "https://api.asgo.click:8443/v1",
            "api_format": "openai",
            "model": "deepseek-v4-pro",
            "api_key": plain_key,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r_create.status_code == 200
    assert plain_key not in r_create.text
    created = r_create.json()["data"]
    provider_id = created["id"]
    assert created["api_key_masked"] == "sk-p****abcd"
    assert created["enabled"] is True

    # 重名冲突 -> 409
    r_dup = await c.post(
        "/api/providers",
        json={
            "name": "deepseek",
            "base_url": "https://api.asgo.click:8443/v1",
            "api_format": "openai",
            "model": "deepseek-v4-pro",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r_dup.status_code == 409

    # 服务端内部可正确解密原文
    async with session_factory() as s:
        svc = ProviderService(s)
        db_obj = await svc.get(provider_id)
        assert db_obj.api_key_enc is not None
        assert plain_key not in db_obj.api_key_enc
        assert svc.get_decrypted_api_key(db_obj) == plain_key

    # 列表与更新（更新模型、禁用、更新密钥）
    r_list = await c.get("/api/providers")
    assert r_list.status_code == 200
    assert r_list.json()["data"]["total"] == 1
    assert plain_key not in r_list.text

    new_key = "sk-updated-new-key-9999"
    r_patch = await c.patch(
        f"/api/providers/{provider_id}",
        json={"enabled": False, "model": "deepseek-r1", "api_key": new_key},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_patch.status_code == 200
    assert new_key not in r_patch.text
    patched = r_patch.json()["data"]
    assert patched["enabled"] is False
    assert patched["model"] == "deepseek-r1"
    assert patched["api_key_masked"] == "sk-u****9999"

    # 删除
    r_del = await c.delete(
        f"/api/providers/{provider_id}", headers={"X-CSRF-Token": csrf}
    )
    assert r_del.status_code == 200
    r_gone = await c.get(f"/api/providers/{provider_id}")
    assert r_gone.status_code == 404
