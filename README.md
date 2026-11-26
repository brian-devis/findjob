# AIJob

AIJob 是一个「AI 任务助理」系统：一个运行在目标 Linux VPS 上的中心服务（FastAPI 后端 + Web 管理后台），负责管理 Agent、任务调度与 AI Provider 接入；用户的 Windows 本机通过一个 Local Agent 经 WSS/HTTPS 与中心服务通信。

## 当前阶段

**P1 —— 后端基础架构开发阶段。** FastAPI 后端骨架已完成（`backend/`），含配置、日志、异常处理、数据库（SQLite WAL）、Alembic 迁移、鉴权（JWT Cookie + argon2id + CSRF）、Agent/Task API、任务状态机、Docker 部署与 pytest 测试。尚未部署，尚未连接 VPS。

## 目录结构

```
backend/
├── app/             # FastAPI 应用（core/models/schemas/services/repositories/api 分层）
├── alembic/         # 数据库迁移
├── tests/           # pytest 测试
├── Dockerfile
├── docker-compose.yml
├── requirements.txt        # 运行时依赖
└── requirements-dev.txt    # 开发/测试依赖
```

## 本地开发

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head          # 建库
.venv/bin/python -m app.cli create-admin --username admin --password xxx
.venv/bin/uvicorn app.main:app --port 8000
.venv/bin/pytest -q                     # 测试
.venv/bin/ruff check app tests          # 代码质量
```

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
