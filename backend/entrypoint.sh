#!/bin/sh
set -e

# 启动前执行数据库迁移
alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
