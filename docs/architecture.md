# AIJob 架构设计（P0）

> 阶段：P0 架构设计。本文档描述目标架构与部署目标环境，不包含任何已在服务器上执行的变更。

## 1. 目标与环境基准

AIJob 部署在目标 Linux VPS 上，复用现有 Caddy 作为唯一公网 HTTPS 入口。

### 1.1 目标服务器（用户提供，部署前必须复检）

| 项 | 值 |
| --- | --- |
| IP | `106.54.194.51` |
| 操作系统 | Ubuntu 24.04.4 LTS |
| 运行内核 | `6.8.0-138`（`6.8.0-151` 待重启生效） |
| 连续运行 | 约 20 天 |
| CPU | 2 核；负载 0.03 / 0.04 / 0.01 |
| 内存 | 约 3.6 GiB 总量；已用 947 MiB；可用约 2.7 GiB |
| 磁盘 | 总量 69 GB；已用 14 GB；使用率 22% |

### 1.2 现有业务（不可影响）

**Docker 容器：**

| 容器 | 状态 | 端口 |
| --- | --- | --- |
| `workbuddy-manager` | Up / healthy | `127.0.0.1:7864` |
| `workbuddy2api` | Up / healthy | `7863`（仅内网） |

**系统服务（全部 active，无失败单元）：** `hbbs`、`hbbr`、`xray-client`、`caddy`、`ssh`、`docker`。

**公网端口：**

| 端口 | 用途 |
| --- | --- |
| 22 | SSH |
| 21115–21119 | RustDesk 信令及中继 |
| 8443 | HTTPS API + 管理面板（主用入口） |
| 80 / 443 | 腾讯备案拦截，**不可用** |

**域名与证书现状：** `asgo.click` 未备案，80/443 被拦截；现有 HTTPS 通过 8443 提供。现有 Caddy 已服务：

- `api.asgo.click`（8443）→ 路径白名单代理到 `127.0.0.1:7864`
- `panel.asgo.click`（8443）→ Basic Auth 代理到 `127.0.0.1:7864`

AIJob 规划接入子域名：`fj.asgo.click`（8443），与上述站点并存，经 Caddy 反向代理到 AIJob FastAPI（仅 127.0.0.1）。

> 现有 Caddyfile 的确切内容、监听端口、反向代理规则与证书，必须在部署前现场复检（见 deployment.md）。**不能假设可直接新增路由。**

## 2. 系统组成

```
Windows Local Agent
   |
   | WSS / HTTPS :8443（经 Caddy 反向代理）
   v
现有 Caddy（唯一公网入口）
   |
   | 反向代理（独立路径 / 子域名，待确认）
   v
AIJob FastAPI（仅监听 127.0.0.1）
   ├── Agent Manager   —— 管理 Windows Local Agent 连接与会话
   ├── Task Manager    —— 任务创建 / 调度 / 状态
   ├── AI Provider     —— 统一封装上游 AI 服务调用
   ├── SQLite          —— 持久化（data/，随卷持久化）
   └── 静态资源服务    —— 托管 React 构建产物（管理后台前端）
```

### 2.1 组件职责

| 组件 | 职责 |
| --- | --- |
| AIJob FastAPI | 后端核心；提供 REST API 与 WSS 端点；托管 React 静态文件 |
| Agent Manager | Local Agent 注册、鉴权、心跳、连接生命周期 |
| Task Manager | 任务模型、调度、执行状态、结果回传 |
| AI Provider | 对上游 AI 服务（多 Provider）的抽象与凭据管理 |
| SQLite | 主数据存储；单文件，置于持久卷 |
| Web 管理后台 | React 构建产物，由 FastAPI 直接服务（减少独立容器） |
| Windows Local Agent | 部署在用户 Windows 本机，主动通过 WSS/HTTPS 连接中心服务 |

## 3. 网络拓扑与约束

- AIJob 服务**只监听 `127.0.0.1`**，不直接对公网开放任何端口。
- 使用**独立 Docker 网络**（Compose 项目 `ai-job-assistant`），不重建、不加入现有网络。
- 公网仅通过现有 Caddy 的 8443 入口到达，AIJob 使用独立子域名 `fj.asgo.click`。
- 80 / 443 一律不使用。

## 4. 资源规划（初步）

| 服务 | CPU 上限 | 内存上限 |
| --- | --- | --- |
| FastAPI（含静态资源服务） | 0.75 核 | 512 MiB |
| Web 静态资源（若独立部署） | 0.25 核 | 128 MiB |
| 系统预留 | 不分配给项目 | 保留足够余量 |

> 优先由 FastAPI 直接托管 React 构建产物，减少一个独立容器。实际部署前结合 Docker 当前资源占用再次评估。

## 5. 数据持久化

SQLite 必须持久化，不能随容器重建丢失。建议宿主目录：

```
/opt/ai-job-assistant/
├── data/      # SQLite 数据库
├── logs/      # 运行日志
├── config/    # 应用配置（含密钥，权限 600）
└── deploy/    # docker-compose.yml 等部署文件
```

## 6. 非功能约束

- 安全性：最小暴露、仅经 Caddy 入口、密钥不落于镜像层（见 security.md）。
- 可维护性：日志轮转、健康检查、优雅停机。
- 兼容性：不升级内核、不重启服务器、不触碰现有业务。
