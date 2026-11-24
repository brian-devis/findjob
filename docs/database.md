# AIJob 数据库设计（P0）

> 阶段：P0 架构设计。本文档定义数据模型与任务状态机，具体 DDL 于 P1 落地。

## 1. 数据库选型与并发模型

- 使用 **SQLite**，文件位于持久卷 `data/`，容器重建不丢。
- 启用 **WAL 模式**（`journal_mode=WAL`），`synchronous=NORMAL`，`busy_timeout` 建议 ≥ 5000ms。
- **单写者**：写操作串行化、保持事务短小；WAL 下读可并发。
- 并发规模定位：1 个管理员 + 少量 Agent + 低频任务。满足此规模无压力。
- **迁移路径**：若未来并发/多实例需求上升，数据库层需抽象，迁移到 PostgreSQL。

## 2. 表结构（草案）

### admins（管理员）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | |
| username | TEXT UNIQUE | 登录名 |
| password_hash | TEXT | argon2id 哈希，绝不存明文 |
| created_at / updated_at | TEXT | |

### agents（Agent）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | |
| agent_id | TEXT UNIQUE | UUID4，对外公开标识 |
| name | TEXT | 显示名 |
| secret_hash | TEXT | Agent 凭据的 argon2id 哈希（不可逆） |
| secret_version | INTEGER | 凭据轮换版本号 |
| status | TEXT | `active` / `revoked` |
| revoked_at / revoked_reason | TEXT/INTEGER | 吊销信息 |
| last_seen_at | TEXT | 最近心跳时间 |
| created_at | TEXT | |

### tasks（任务）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | |
| task_id | TEXT UNIQUE | UUID4，对外标识 + 幂等键 |
| agent_id | TEXT | 目标 Agent（FK 到 agents.agent_id） |
| type | TEXT | 任务类型 |
| status | TEXT | 见状态机 |
| payload | TEXT(JSON) | 任务输入 |
| result | TEXT(JSON) | 成功结果 |
| error | TEXT | 失败原因 |
| priority | INTEGER | 优先级 |
| attempt | INTEGER | 已尝试次数 |
| max_attempts | INTEGER | 最大重试次数 |
| timeout_seconds | INTEGER | 执行超时 |
| lease_expires_at | TEXT | 分发租约到期时间 |
| idempotency_key | TEXT UNIQUE | 客户端幂等键（可选） |
| scheduled_at | TEXT | 延迟执行时间（可选） |
| created_at / dispatched_at / started_at / finished_at | TEXT | 时间戳 |

### ai_providers（AI Provider）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | |
| name | TEXT | Provider 名 |
| base_url | TEXT | 服务地址 |
| api_format | TEXT | `openai` / `anthropic` |
| model | TEXT | 模型标识 |
| api_key_enc | TEXT | **加密存储**（AES-GCM，主密钥来自 config/），非哈希 |
| enabled | INTEGER | 是否启用 |
| created_at | TEXT | |

> 区分：Agent 凭据用于「认证」，哈希存储（不可逆）；Provider API Key 用于「调用」，需解密使用，故加密存储（可逆）。二者都不能以明文写入日志或返回前端。

### audit_log（审计）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | |
| ts | TEXT | |
| actor | TEXT | 操作者（admin / agent_id） |
| action | TEXT | 操作类型 |
| target | TEXT | 作用对象 |
| detail | TEXT(JSON) | 详情（不含密钥） |

## 3. 任务状态机

```
                  +-----------+  dispatch   +------------+   ack    +---------+
   create ------->|  queued   |-----------> | dispatched |--------> | running |
                  +-----------+             +------------+          +---------+
                       |  |                     |                       |    \
        cancel         |  | lease expiry         | lease expiry          |     \ result
                       v  | (no ack)             | (running 后掉线)       |      v
                  +-----------+                  +----------+            |   +-----------+
                  | cancelled |                  |  requeue |<-----------+-->| succeeded |
                  +-----------+                  +----------+ (重试)      |   +-----------+
                                                                        |
                                                                        +--> +--------+
                                                                             | failed  |
                                                                             +--------+
```

状态集合：`queued`、`dispatched`、`running`、`succeeded`、`failed`、`cancelled`。

| 状态 | 含义 | 出口 |
| --- | --- | --- |
| `queued` | 已入队待分发 | → `dispatched`；→ `cancelled` |
| `dispatched` | 已下发，等待 Agent ack | ack → `running`；租约到期 → `queued`（重分配） |
| `running` | Agent 已确认并执行中 | 结果 → `succeeded`/`failed`；超时 → `failed` |
| `succeeded` | 终态 | — |
| `failed` | 失败（含超时） | `attempt < max_attempts` 时 → `queued`（attempt+1），否则终态 |
| `cancelled` | 已取消（管理员或超时） | — |

## 4. 幂等与去重

- **创建幂等**：客户端可选传 `idempotency_key`，重复提交返回已有任务，不重复创建。
- **执行幂等**：Agent 以 `task_id` 为幂等键，已完成的任务不重复执行。
- **结果去重**：服务端对已终态的任务再次收到结果时忽略（返回当前状态），避免重复写。

## 5. 一致性与索引

- `tasks(status, priority)`、`tasks(agent_id)`、`tasks(lease_expires_at)` 建索引，支持分发扫描。
- 分发与租约更新在**短事务**内完成，避免长事务锁库。
