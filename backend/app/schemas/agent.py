"""Agent 相关 schema。"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class AgentOut(ORMModel):
    agent_id: str
    name: str
    status: str
    secret_version: int
    last_seen_at: datetime | None = None
    created_at: datetime


class AgentSecretOut(BaseModel):
    agent_id: str
    secret: str
