"""Local Agent 配置加载（环境变量 / .env）。"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIJOB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server_ws_url: str = Field(
        default="wss://fj.asgo.click:8443/ws/agent",
        min_length=1,
    )
    agent_id: str = Field(min_length=1, max_length=64)
    agent_secret: str = Field(min_length=1)

    state_db_path: str = "./data/agent_state.db"
    heartbeat_interval_seconds: float = Field(default=20.0, gt=0)
    recv_timeout_seconds: float = Field(default=45.0, gt=0)
    reconnect_base_seconds: float = Field(default=1.0, gt=0)
    reconnect_max_seconds: float = Field(default=60.0, gt=0)
    log_level: str = "INFO"

    @property
    def masked_secret(self) -> str:
        """返回脱敏后的 secret 掩码，禁止在日志中打印完整凭据。"""
        secret = self.agent_secret
        if len(secret) <= 6:
            return "****"
        return f"{secret[:3]}****{secret[-3:]}"
