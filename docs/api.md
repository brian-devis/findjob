# AIJob REST API 设计（P0）

> 阶段：P0 架构设计。定义管理后台与后端之间的 REST 接口，具体路径与字段于 P1 定稿。

## 1. 约定

- 前缀 `/api`，JSON 收发。
- 管理接口需管理员认证（JWT，HttpOnly Cookie）；状态变更接口需额外 CSRF 防护（见 security.md）。
- **所有返回一律不回显明文密钥**：Provider API Key、Agent secret 只返回掩码（如 `sk-****abc`），仅创建/轮换时一次性返回完整值。

## 2. 鉴权（admin）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 用户名 + 密码 → 设置 access/refresh cookie |
| POST | `/api/auth/logout` | 注销，吊销 refresh |
| POST | `/api/auth/refresh` | 用 refresh cookie 换新 access |
| GET | `/api/auth/me` | 当前管理员信息 |

## 3. Agent 管理（admin）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/agents` | 注册 Agent → 返回 `agent_id` + 一次性 `agent_secret` |
| GET | `/api/agents` | 列表（含状态、last_seen） |
| GET | `/api/agents/{agent_id}` | 详情（凭据仅掩码） |
| POST | `/api/agents/{agent_id}/rotate-secret` | 轮换凭据 → 返回新 `agent_secret`（一次性） |
| POST | `/api/agents/{agent_id}/revoke` | 吊销（断开连接并拒绝重连） |
| DELETE | `/api/agents/{agent_id}` | 删除 |

## 4. 任务管理（admin）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/tasks` | 创建任务（可带 `idempotency_key`） |
| GET | `/api/tasks` | 任务列表（分页、按状态过滤） |
| GET | `/api/tasks/{task_id}` | 任务详情（含 result / error） |
| POST | `/api/tasks/{task_id}/cancel` | 取消任务 |

## 5. AI Provider 管理（admin）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/providers` | 新建 Provider（`api_key` 一次性返回） |
| GET | `/api/providers` | 列表（`api_key` 掩码） |
| PATCH | `/api/providers/{id}` | 更新配置 |
| DELETE | `/api/providers/{id}` | 删除 |

## 6. 健康检查

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/healthz` | 存活探针（无需认证） |
| GET | `/api/healthz` | 就绪探针（可含 DB 连通性） |

## 7. WebSocket

| 路径 | 说明 |
| --- | --- |
| `/ws/agent` | Agent 长连接，协议见 `websocket-protocol.md` |

## 8. 安全要点

- 状态变更接口（POST/PATCH/DELETE）需 CSRF 防护。
- 密码、secret、API Key 均不入响应日志、不落明文。
- 审计日志记录关键操作（登录、注册、轮换、吊销、任务创建/取消），不含密钥。
