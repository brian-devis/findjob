# AIJob

AIJob 是一个「AI 任务助理」系统：运行在 Linux VPS 上的中心服务（FastAPI 后端 + React 管理后台 + SQLite WAL），负责管理 Agent、任务调度、审计日志与 AI Provider 接入；用户的 Windows 本机通过轻量级 Local Agent 经 WSS/HTTPS 与中心服务双向通信。

## 当前阶段

**P2 —— 核心功能开发完成。** 中心服务（`backend/`）、Windows Local Agent（`agent/`）与 React 管理后台（`frontend/`）核心链路已就绪，正在 PR #4 审查阶段，尚未部署至目标 VPS。

### 核心能力

- **中心控制面（`backend/`）**
  - **管理后台鉴权**：argon2id 密码哈希、JWT（access 15m + refresh 7d）写入 HttpOnly + SameSite=Strict Cookie、`token_version` 登出全吊销、双提交 CSRF（`X-CSRF-Token`）及安全响应头（CSP / nosniff / X-Frame-Options）。
  - **Agent WebSocket 协议（`/ws/agent`）**：`X-Agent-Id` + `Authorization: Bearer` 握手鉴权（先验密码再检查吊销状态防探测）、应用层 `ping`/`pong` 心跳保活（连续超时 `4003` 断开）、`task_dispatch` / `task_ack` / `task_result` / `task_cancel` 闭环、凭据轮换或吊销时立即强制断开在线连接。
  - **任务调度与恢复循环**：事件唤醒 + 定时轮询兜底，支持优先级调度、轮询分配在线 Agent、原子条件抢占、`dispatched` 租约过期回收、`running` 超时自动重试/失败终态与下发失败回滚。
  - **AI Provider 管理（`/api/providers`）**：支持 `openai` / `anthropic` 格式配置，`api_key` 使用 AES-256-GCM 加密存储（可配置独立 `PROVIDER_MASTER_KEY` 或通过 HKDF 派生），所有接口仅返回掩码。
  - **审计日志（`/api/audit-logs`）**：记录登录/登出、Agent 注册/轮换/吊销/删除、任务创建/取消及 Provider 变更，内置递归敏感字段脱敏。
  - **前端静态托管与多阶段 Docker**：FastAPI 自动挂载 `frontend/dist`（或 `STATIC_DIR`）并提供 SPA history fallback，不引入 Nginx。
- **Windows Local Agent（`agent/`）**
  - **持久幂等去重**：基于本地 SQLite WAL（`executed_tasks`）记录已完成任务与上报状态，同一 `task_id` 重复下发不重复执行，断线期间结果在重连后自动补报。
  - **断线恢复**：指数退避 + 抖动重连，收到 `4001`（鉴权失败）/ `4002`（已吊销）后停止无效重试。
  - **内置执行器**：零第三方监控依赖实现 `PING` 与 `SYSTEM_INFO`，支持超时控制与 `task_cancel` 中断。
- **React 管理后台（`frontend/`）**
  - Vite + React 19 + TypeScript 实现，覆盖管理员登录、Agent 在线状态/一次性凭据引导与密钥轮换吊销、任务筛选/创建/JSON 详情/取消、AI Provider 配置及审计日志筛选视图。

## 目录结构

```
AIJob/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # REST 路由：health / auth / agents / tasks / providers / audit
│   │   ├── core/            # 配置、日志、异常、安全、AES-GCM 加密、数据库 WAL、UTC 时间
│   │   ├── models/          # SQLAlchemy 模型：Admin / Agent / Task / AIProvider / AuditLog
│   │   ├── repositories/    # 数据访问与原子任务抢占查询
│   │   ├── schemas/         # Pydantic 校验与响应模型
│   │   ├── services/        # 业务逻辑与后台 TaskScheduler 调度循环
│   │   └── ws/              # Agent WebSocket 端点（/ws/agent）、协议校验与连接管理器
│   ├── alembic/             # 数据库迁移（dacdf03f3fdf 初始表 + b7e4c1a9f203 审计日志表）
│   ├── tests/               # pytest 测试（38 个用例）
│   ├── Dockerfile           # 多阶段构建（Node 构建 frontend + Python FastAPI 静态托管）
│   ├── docker-compose.yml   # 独立 Compose 项目 ai-job-assistant（仅绑 127.0.0.1:8100）
│   ├── .env.example
│   ├── requirements.txt
│   └── requirements-dev.txt
├── agent/
│   ├── agent/               # Local Agent 客户端、SQLite 去重存储、执行器与 CLI 入口
│   ├── tests/               # pytest 测试（8 个用例，含真实 FastAPI 端到端联调）
│   ├── .env.example
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── src/                 # React + TypeScript 管理后台源码
│   ├── package.json
│   └── vite.config.ts
└── docs/                    # P0 架构、部署、安全、数据库、WebSocket 与 API 设计文档
```

## 快速开始（本地开发与联调）

### 1. 构建前端产物

```bash
cd frontend
npm ci
npm run build                # 输出到 frontend/dist，由 FastAPI 自动托管
# 开发模式热更新（代理 /api 与 /healthz 到 127.0.0.1:8000）：
# npm run dev
```

### 2. 启动中心后端

```bash
cd backend
cp .env.example .env         # 必填 JWT_SECRET（至少 32 字符随机密钥，可用 openssl rand -hex 32 生成）
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli create-admin --username admin --password your-strong-password
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开浏览器访问 `http://127.0.0.1:8000` 即可进入管理后台。

### 3. 启动 Local Agent

在管理后台「Agents」页注册一个新 Agent，复制页面一次性展示的 `AIJOB_AGENT_ID` 与 `AIJOB_AGENT_SECRET`：

```bash
cd agent
cp .env.example .env         # 设置 AIJOB_SERVER_WS_URL=ws://127.0.0.1:8000/ws/agent 及上述凭据
python3 -m venv .venv
# Windows: .venv\Scripts\pip install -r requirements.txt && .venv\Scripts\python -m agent.main
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m agent.main
```

### 4. 验证闭环

1. 管理后台「Agents」列表中该 Agent 显示「在线」且更新 `last_seen_at`；
2. 在「任务队列」创建 `PING` 或 `SYSTEM_INFO` 任务，调度器立即通过 WebSocket 下发并在数秒内回传结果；
3. 在「审计日志」页可按动作查看登录、注册、任务下发与 Provider 操作记录。

### Docker 多阶段构建参考（仅用于目标主机部署）

```bash
cd backend
cp .env.example .env         # 配置生产 JWT_SECRET 与 COOKIE_SECURE=true
docker compose build
docker compose up -d
```

## 测试与代码质量

```bash
# 后端单元测试与 Lint（当前 38 passed）
cd backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests

# Local Agent 测试与 Lint（当前 8 passed；E2E 用例需同时安装 backend 依赖，缺失时自动跳过）
cd agent
../backend/.venv/bin/python -m pytest -q
../backend/.venv/bin/ruff check agent tests

# 前端类型检查与生产构建
cd frontend
npm run build
```

## 主要接口速览

| 模块 | 路径 | 说明 |
| --- | --- | --- |
| 健康检查 | `GET /healthz`、`GET /api/healthz` | 存活与数据库就绪探针 |
| 管理员鉴权 | `POST /api/auth/{login,logout,refresh}`、`GET /api/auth/me` | JWT Cookie + CSRF 鉴权 |
| Agent 管理 | `POST/GET /api/agents`、`GET/DELETE /api/agents/{agent_id}`、`POST /api/agents/{agent_id}/{rotate-secret,revoke}` | 注册、在线状态、轮换与吊销 |
| 任务管理 | `POST/GET /api/tasks`、`GET /api/tasks/{task_id}`、`POST /api/tasks/{task_id}/cancel` | 创建（幂等）、状态追踪与取消 |
| AI Provider | `POST/GET /api/providers`、`GET/PATCH/DELETE /api/providers/{id}` | AES-GCM 加密存储与掩码返回 |
| 审计日志 | `GET /api/audit-logs` | 按操作者/动作分页检索 |
| Agent 长连接 | `WS /ws/agent` | 握手鉴权、心跳与任务双向信令 |

## 文档索引

| 文档 | 说明 |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | 系统架构、组件、网络拓扑、关键决策、目标 VPS 环境基准 |
| [docs/deployment.md](docs/deployment.md) | Docker Compose 部署设计、目录规划、端口与 8443 接入方案 |
| [docs/security.md](docs/security.md) | 安全设计：网络边界、管理后台鉴权、Agent 凭据、密钥、最小权限 |
| [docs/database.md](docs/database.md) | SQLite 数据模型与任务状态机 |
| [docs/websocket-protocol.md](docs/websocket-protocol.md) | Agent WSS 协议：鉴权、心跳、幂等、断线恢复 |
| [docs/api.md](docs/api.md) | REST API 设计 |
| [docs/development-plan.md](docs/development-plan.md) | P0 / P1 / P2 阶段计划、决策状态与遗留项 |

## 目标服务器（用户提供的环境基准）

- IP：`106.54.194.51`
- 系统：Ubuntu 24.04.4 LTS，内核 `6.8.0-138`（`6.8.0-151` 待重启生效）
- 资源：2 核 CPU，约 3.6 GiB 内存（可用约 2.7 GiB），磁盘 69 GB（已用 14 GB / 22%）
- 已存在业务（**必须保持正常运行**）：`workbuddy-manager`（127.0.0.1:7864）、`workbuddy2api`（内网 7863）
- 已存在系统服务：`hbbs` / `hbbr`（RustDesk）、`xray-client`、`caddy`、`ssh`、`docker`
- 公网端口：22（SSH）、21115–21119（RustDesk）、8443（HTTPS API + 管理面板）；80/443 因未备案被腾讯拦截
- AIJob 接入子域名：`fj.asgo.click`（8443），经现有 Caddy 反向代理

> 注意：以上信息是用户提供的环境基准，**不是**已完成的服务器检查结果。真正部署前必须重新检查（详见 deployment.md 的「部署前检查清单」）。

## 关键架构决策（P0）

1. **端口**：容器内 8000，宿主仅绑 `127.0.0.1:8100`（候选，P1 复核），公网经 Caddy 8443（`fj.asgo.click`）。
2. **管理后台鉴权**：应用内 JWT（HttpOnly Cookie）+ argon2id 密码 + CSRF/XSS 防护，不回显明文密钥。
3. **Agent 凭据**：UUID4 + 独立 secret（哈希存储、轮换、吊销、WS 握手鉴权）。
4. **静态资源**：React 构建由 FastAPI 托管，不引入 Nginx 容器。

详见 [docs/architecture.md](docs/architecture.md)。

## 硬性约束（P0 起生效）

- 不删除、不停止、不修改现有 Docker 容器（workbuddy-manager / workbuddy2api）。
- 不占用现有服务端口；不使用 80/443。
- 不重建现有 Docker 网络；AIJob 使用独立的 Docker Compose 项目 `ai-job-assistant`。
- 不直接暴露 FastAPI 端口、WebSocket 端口到公网。
- 未经确认不修改现有 Caddy 配置；新增路由必须先检查现有配置并等待确认。
- 未经确认不执行 reboot / shutdown / 内核更新 / 系统升级。
