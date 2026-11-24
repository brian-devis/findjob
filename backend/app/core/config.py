"""应用配置：通过环境变量 / .env 加载。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "AIJob"
    debug: bool = False
    api_prefix: str = "/api"

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./data/aijob.db"

    # 安全
    jwt_secret: str = "change-me-in-production-use-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cookie_secure: bool = False
    cookie_samesite: str = "strict"

    # 日志
    log_level: str = "INFO"

    # 首次启动管理员引导（可选，仅当 admin 不存在时创建）
    admin_username: str | None = None
    admin_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
