# AIJob WebSocket 协议（P0）

> 阶段：P0 架构设计。定义 Windows Local Agent 与中心服务之间的 WSS 协议，含鉴权、心跳、幂等与断线恢复。

## 1. 端点与鉴权

- 地址：`wss://fj.asgo.click/ws/agent`（经 Caddy 8443 反向代理，TLS 由 Caddy 终止）。
- 握手时携带请求头：
  - `X-Agent-Id: <agent_id>`（UUID）
  - `Authorization: Bearer <agent_secret>`
- 服务端按 `agent_id` 查 Agent，用 `secret_hash` 校验 `agent_secret`；`status != active` 或校验失败即拒绝并关闭（见关闭码）。
- 鉴权失败 / 已吊销的 Agent 不得建立连接。

## 2. 消息封装

文本帧，JSON 对象：

```json
{ "type": "<消息类型>", "id": "<消息唯一id，可选>", "data": { ... } }
```

## 3. 消息类型

### 服务端 → Agent

| type | data | 说明 |
| --- | --- | --- |
| `auth_ok` | `{agent_id}` | 鉴权成功 |
| `auth_error` | `{reason}` | 鉴权失败（随后关闭） |
| `pong` | `{}` | 心跳应答 |
| `task_dispatch` | `{task_id, type, payload, timeout_seconds}` | 下发任务 |
| `task_cancel` | `{task_id}` | 取消任务 |
| `error` | `{code, message}` | 协议错误 |

### Agent → 服务端

| type | data | 说明 |
| --- | --- | --- |
| `ping` | `{}` | 心跳（或回应服务端 ping 的 `pong`） |
| `task_ack` | `{task_id}` | 确认接收并开始执行 |
| `task_result` | `{task_id, status: "succeeded"\|"failed", result?, error?}` | 执行结果 |
| `task_progress` | `{task_id, progress}` | 可选进度上报 |

## 4. 心跳与存活

- 服务端每 30s 发 `pong`/ping；Agent 需在超时（如 10s）内应答。
- 连续 3 次无应答 → 服务端主动关闭连接（关闭码 `4003`）。
- Agent 侧也应设心跳，长时间无服务端消息时判定连接已断并重连。

## 5. 任务分发与幂等（防止重复执行）

采用 **至少一次投递 + 幂等执行 = 效果上恰好一次**：

1. 服务端把任务置为 `dispatched`，设 `lease_expires_at`，下发 `task_dispatch`。
2. Agent 收到后立即回 `task_ack`，服务端置为 `running`。
3. 若 ack 丢失：服务端在租约到期后把任务重新入队（`queued`），可能再次 `task_dispatch` 给同一或另一 Agent。
4. **Agent 以 `task_id` 幂等**：对已执行完成的任务不再重复执行；若已完成但结果未送达，重连后重发 `task_result`。
5. **服务端结果去重**：已终态的任务再收到 `task_result` 时忽略（返回当前状态）。

## 6. 断线恢复

- Agent 断线后自动重连，采用**指数退避 + 抖动**（如 1s、2s、4s … 上限 60s）。
- 重连后重新鉴权；服务端通过 `task_id` 幂等保证不会因重连导致任务重复执行。
- 服务端在 Agent 断线后：其处于 `dispatched` / `running` 的任务随租约到期自动重分配；执行中的任务结果若未上报，由 Agent 重连后补报。
- 避免重复执行的关键在 **Agent 本地持久化 task_id 执行记录**（至少内存级，建议落盘），P1 需落实。

## 7. 关闭码

| 码 | 含义 |
| --- | --- |
| 1000 | 正常关闭 |
| 1001 | 服务端维护 / Agent 主动下线 |
| 4001 | 鉴权失败 |
| 4002 | Agent 已被吊销 |
| 4003 | 心跳超时 |
| 4004 | 协议错误（非法消息） |

## 8. 安全

- 连接必须鉴权；未鉴权不进入业务消息处理。
- 日志只记录 `agent_id` 与凭据掩码，**不记录完整 secret**。
- 消息 payload 不落日志；如需审计只记 `task_id` 与结果摘要。
