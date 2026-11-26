# AIJob

AIJob（仓库名 `findjob`）是一款面向个人求职的 **AI 智能求职与简历投递系统**：由运行在 Linux VPS 上的中心服务（FastAPI + React 管理后台 + SQLite WAL）统筹 AI 能力与任务调度，配合运行在用户 Windows 本机的 Local Agent 接入 **BOSS 直聘**，完成从「AI 审阅修改简历 → 同步更新至 BOSS 直聘 → 匹配岗位并自动投递」的完整闭环。

## 核心业务流程

1. **AI 审阅与修改简历**：通过后台接入的 AI Provider 对个人简历进行结构诊断、亮点提炼与岗位定向改写，形成确认版本。
2. **简历同步至 BOSS 直聘**：中心服务下发同步任务至用户 Windows 本机 Local Agent，将审阅修改后的简历内容同步更新到 BOSS 直聘在线简历。
3. **相关岗位筛选与自动投递**：Local Agent 抓取/检索符合条件的 BOSS 直聘岗位，结合 AI 匹配度评分与定制化打招呼话术，按限频防重策略自动投递并回传状态。
   - **安全与合规边界**：平台登录或人机验证必须在用户本机可见浏览器中由人工完成，系统暂停等待确认后继续，不实现任何绕过验证码或平台风控的能力。

```
┌──────────────────────────┐        HTTPS        ┌──────────────────────────────────┐
│  React 管理后台 (Web UI) │ ◄─────────────────► │  Linux VPS 中心服务 (FastAPI)     │
│  简历/岗位/Agent/Provider│                     │  - 鉴权 / AES-GCM Key / 审计日志  │
└──────────────────────────┘                     │  - AI Provider 调度（审阅/匹配）  │
                                                 │  - 任务调度循环 & /ws/agent 网关  │
                                                 └───────────────▲──────────────────┘
                                                                 │ WSS (8443/Caddy)
                                                                 ▼
┌──────────────────────────┐       本机可见浏览器  ┌──────────────────────────────────┐
│       BOSS 直聘          │ ◄─────────────────► │  Windows Local Agent (本机常驻)   │
│  在线简历 / 岗位 / 投递  │                     │  - 简历同步 / 岗位采集 / 自动投递  │
└──────────────────────────┘                     │  - SQLite WAL 幂等防重复投递       │
                                                 └──────────────────────────────────┘
```

## 当前阶段与路线图

- **已完成（P1–P2 系统底座，PR #4 待合并）**：
  - **中心后端（`backend/`）**：JWT HttpOnly Cookie + argon2id + CSRF 双提交鉴权、Agent 注册/轮换/吊销、`/ws/agent` 双向协议与心跳、事件驱动任务调度与租约/超时恢复循环、AI Provider（AES-256-GCM 加密存储）、操作审计日志（`audit_logs` 敏感键脱敏）、FastAPI 静态 SPA 托管与多阶段 Docker 构建。
  - **Windows Local Agent（`agent/`）**：WSS 握手鉴权、指数退避重连、SQLite WAL 本地任务去重与断线补报，以及基础连通性执行器（`PING`、`SYSTEM_INFO`）。
  - **React 管理后台（`frontend/`）**：登录、Agent 在线管理与一次性凭据引导、任务队列创建与追踪、AI Provider 配置、审计日志查看。
- **已本地实现（P3 BOSS 直聘业务闭环，`feature/aijob-p3-resume-ai` 分支）**：
  - **P3-1 简历工作台与 AI 审阅改写**：支持 Word（`.docx`）、PDF（`.pdf`）、Markdown/TXT 上传解析（≤ 5MB）与版本管理，通过已配置的 AI Provider 进行结构诊断打分、定向改写生成优化版本，并支持导出为 Word（`.docx`）/ Markdown（`.md`）；
  - **P3-2 Windows 本地持久化浏览器与简历同步**：基于可见桌面 Chrome/Edge 持久化配置目录（`PersistentBrowserManager`）复用登录态，支持 `BOSS_CHECK_LOGIN` 登录检测与 `BOSS_SYNC_RESUME` 在线简历同步（默认 `dry_run` 预演，遇未登录/安全验证立即暂停交由人工接管）；
  - **P3-3 岗位扫描、AI 匹配与可切换投递漏斗**：配置求职偏好（`job_preferences`）与公司/关键词黑名单、采集 BOSS 岗位并幂等入库（`boss_jobs`）、单条及批量 AI 评分与个性化打招呼文案生成，默认**手动逐条确认投递**，支持开关一键切换为**高分自动错峰投递**并严格校验每日投递上限。

> 当前代码尚未部署至目标 VPS。

## 目录结构

```
AIJob/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # REST 路由：health / auth / agents / tasks / providers / resumes / jobs / audit
│   │   ├── core/            # 配置、日志、异常、安全、AES-GCM 加密、数据库 WAL、UTC 时间
│   │   ├── models/          # SQLAlchemy 模型：Admin / Agent / Task / AIProvider / Resume / JobPreference / BossJob / AuditLog
│   │   ├── repositories/    # 数据访问与原子任务抢占/配额统计查询
│   │   ├── schemas/         # Pydantic 校验与响应模型
│   │   ├── services/        # 业务逻辑、AI 客户端与后台 TaskScheduler 调度循环
│   │   └── ws/              # Agent WebSocket 端点（/ws/agent）、协议校验与状态回调
│   ├── alembic/             # 数据库迁移（dacdf03f3fdf → b7e4c1a9f203 → c9a2f4d8e105 → d4b7e2f9a312）
│   ├── tests/               # pytest 测试（46 个用例）
│   ├── Dockerfile           # 多阶段构建（Node 构建 frontend + Python FastAPI 静态托管）
│   ├── docker-compose.yml   # 独立 Compose 项目 ai-job-assistant（仅绑 127.0.0.1:8100）
│   ├── .env.example
│   ├── requirements.txt
│   └── requirements-dev.txt
├── agent/
│   ├── agent/               # Windows Local Agent 客户端、持久化浏览器管理、BOSS/基础执行器与 SQLite 去重存储
│   ├── tests/               # pytest 测试（13 个用例，含真实 FastAPI 端到端联调）
│   ├── start-windows.ps1    # Windows 一键初始化与启动脚本
│   ├── .env.example
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── src/                 # React + TypeScript 管理后台（ResumesPanel / JobsPanel / AgentsPanel / TasksPanel / ProvidersPanel / AuditPanel）
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

### 3. 启动 Windows Local Agent

在管理后台「Agents」页注册一个 Agent，复制页面一次性展示的 `AIJOB_AGENT_ID` 与 `AIJOB_AGENT_SECRET`：

```bash
cd agent
cp .env.example .env         # 设置 AIJOB_SERVER_WS_URL=ws://127.0.0.1:8000/ws/agent 及上述凭据
python3 -m venv .venv
# Windows: .venv\Scripts\pip install -r requirements.txt && .venv\Scripts\python -m agent.main
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m agent.main
```

### 4. 验证底座闭环

1. 管理后台「Agents」列表中该 Agent 显示「在线」且更新 `last_seen_at`；
2. 在「任务队列」创建 `PING` 或 `SYSTEM_INFO` 任务，调度器立即通过 WebSocket 下发并在数秒内回传结果；
3. 在「AI Providers」配置模型接口（API Key 经 AES-256-GCM 加密存储，列表仅展示掩码）；
4. 在「审计日志」页按操作类型检索登录、Agent、任务与 Provider 变更记录。

### Docker 多阶段构建参考（仅用于目标主机部署）

```bash
cd backend
cp .env.example .env         # 配置生产 JWT_SECRET 与 COOKIE_SECURE=true
docker compose build
docker compose up -d
```

## 测试与代码质量

```bash
# 后端单元测试与 Lint（46 passed）
cd backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests

# Local Agent 测试与 Lint（13 passed；E2E 用例需同时安装 backend 依赖，缺失时自动跳过）
cd agent
PYTHONPATH=. ../backend/.venv/bin/python -m pytest -q
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
| Agent 管理 | `POST/GET /api/agents`、`GET/DELETE /api/agents/{agent_id}`、`POST /api/agents/{agent_id}/{rotate-secret,revoke,check-boss-login}` | 注册、在线状态、轮换、吊销与 BOSS 登录检测 |
| 简历工作台 | `GET/POST /api/resumes`、`POST /api/resumes/upload`、`PATCH/DELETE /api/resumes/{id}`、`POST /api/resumes/{id}/{activate,ai-review,ai-rewrite,sync-boss}` | Word/PDF/文本解析、AI 审阅改写与 BOSS 同步 |
| 岗位与投递 | `GET/PUT /api/jobs/preferences`、`GET /api/jobs`、`POST /api/jobs/{import,scan,auto-apply}`、`POST /api/jobs/{id}/{ai-score,apply,skip}` | 求职偏好、手动/自动切换开关、AI 评分与投递漏斗 |
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
- 平台合规边界：不实现任何绕过 BOSS 直聘登录校验、验证码或风控挑战的功能；遇验证挑战时暂停任务并在用户本机可见浏览器中由人工完成。
