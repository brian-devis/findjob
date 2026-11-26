"""API v1 路由聚合。"""
from fastapi import APIRouter

from app.api.v1 import agents, audit, auth, health, providers, tasks

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(providers.router, prefix="/providers", tags=["providers"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["audit"])
