# AGENTS.md

本文件为在此仓库中工作的 AI 助手与开发者提供约定与边界。

## 项目概况

AIJob：运行在 Linux VPS 上的中心服务（FastAPI + React 管理后台 + SQLite），管理 Windows Local Agent、任务调度与 AI Provider 接入。Agent 通过 WSS/HTTPS（经 Caddy 8443）与中心通信。

## 当前阶段

**P2 核心功能开发阶段。** 仓库包含三部分：
- `backend/`：FastAPI 应用（`app/{core,models,schemas,services,repositories,api,ws}`），含 WS 服务端、任务调度循环、AI Provider（AES-GCM 加密）、审计日志（`audit_logs`）与静态 SPA 托管；
- `agent/`：Windows Local Agent（WSS 接入、SQLite WAL 幂等去重、`PING`/`SYSTEM_INFO` 执行器）；
- `frontend/`：React + TypeScript 管理后台，由多阶段 `backend/Dockerfile` 构建并交由 FastAPI 托管。

## 文档约定

- 设计文档位于 `docs/`，以 Markdown 编写，中文为主。
- 关键决策与事实需在文档中写明「已确认 / 待确认 / 用户提供基准」三类状态。
- 涉及目标 VPS（`106.54.194.51`）的信息是**用户提供的环境基准**，部署前必须复检，不得当作已完成检查。

## 硬性边界（必须遵守）

- 未经用户确认，**不得** SSH 登录服务器、修改 Caddy、创建服务器目录、创建 Docker 容器、执行部署、重启服务器、执行内核更新或系统升级。
- 不删除 / 停止 / 修改现有容器（`workbuddy-manager`、`workbuddy2api`）与现有网络。
- 不占用现有端口，不使用 80/443。
- 公网仅经现有 Caddy 的 8443 入口（子域名 `fj.asgo.click`）。
- 不在文档中记录明文密钥、token、API Key。

## 提交与分支

- 默认分支 `main` 受分支保护，需 `ai-review` 状态检查通过才能合并。
- **未经用户明确要求，不要 commit / push**；仅进行本地文件编辑时不得擅自提交。

## 代码阶段约定（P1 起）

- 后端：Python 3.12 + FastAPI + uvicorn；依赖 `backend/requirements.txt`（运行时）与 `backend/requirements-dev.txt`（开发/测试）。
- 前端：React（TypeScript），构建产物由 FastAPI 托管。
- 数据：SQLite（WAL 模式），模式见 `docs/database.md`；迁移用 Alembic。
- 测试：`pytest`；Lint：`ruff`。
- 常用命令（在 `backend/` 下执行）：
  - `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`
  - `.venv/bin/alembic upgrade head`
  - `.venv/bin/python -m app.cli create-admin --username <u> --password <p>`
  - `.venv/bin/uvicorn app.main:app --port 8000`
  - `.venv/bin/pytest -q`
  - `.venv/bin/ruff check app tests`
