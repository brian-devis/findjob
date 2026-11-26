"""AI Provider 相关 Schema。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

ApiFormat = Literal["openai", "anthropic"]


def _validate_http_url(value: str) -> str:
    v = value.strip()
    if not v.startswith(("https://", "http://")):
        raise ValueError("base_url 必须以 http:// 或 https:// 开头")
    return v


def _validate_non_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        raise ValueError("字段不能为空白字符串")
    return stripped


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=1, max_length=255)
    api_format: ApiFormat = "openai"
    model: str = Field(min_length=1, max_length=64)
    api_key: str | None = Field(default=None, max_length=512)
    enabled: bool = True

    @field_validator("name", "model")
    @classmethod
    def _check_non_blank(cls, v: str) -> str:
        res = _validate_non_blank(v)
        assert res is not None
        return res

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, v: str) -> str:
        return _validate_http_url(v)


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    base_url: str | None = Field(default=None, min_length=1, max_length=255)
    api_format: ApiFormat | None = None
    model: str | None = Field(default=None, min_length=1, max_length=64)
    api_key: str | None = Field(default=None, max_length=512)
    enabled: bool | None = None

    @field_validator("name", "model")
    @classmethod
    def _check_non_blank(cls, v: str | None) -> str | None:
        return _validate_non_blank(v)

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_http_url(v)


class ProviderOut(ORMModel):
    id: int
    name: str
    base_url: str
    api_format: str
    model: str
    api_key_masked: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime
