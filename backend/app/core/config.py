"""应用配置：通过环境变量 / .env 加载。"""
from functools import lru_cache

from pydantic import model_validator
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

    # 安全：JWT_SECRET 无默认值，必须在环境变量 / .env 中显式配置强密钥
    jwt_secret: str = ""
    # AI Provider API Key 加密主密钥（可选；未配置时通过 HKDF 从 jwt_secret 域隔离派生）
    provider_master_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cookie_secure: bool = False
    cookie_samesite: str = "strict"

    # 日志
    log_level: str = "INFO"

    # 前端静态产物目录（为空时自动探测 ../frontend/dist）
    static_dir: str | None = None

    # WebSocket 与任务调度
    ws_heartbeat_interval_seconds: float = 30.0
    ws_heartbeat_timeout_seconds: float = 10.0
    ws_heartbeat_max_missed: int = 3
    scheduler_enabled: bool = True
    scheduler_poll_interval_seconds: float = 2.0
    task_dispatch_lease_seconds: int = 30

    # 首次启动管理员引导（可选，仅当 admin 不存在时创建）
    admin_username: str | None = None
    admin_password: str | None = None

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> "Settings":
        if not self.jwt_secret or len(self.jwt_secret) < 32:
            raise ValueError(
                "JWT_SECRET 未配置或过短：必须设置为至少 32 字符的随机强密钥"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
