# AIJob 安全设计（P0）

> 阶段：P0 架构设计。本文档定义安全原则与边界，具体实现于 P1 落地。

## 1. 网络边界

- AIJob 服务**只监听 `127.0.0.1`**，不向公网暴露任何端口。
- 公网唯一入口为现有 Caddy（8443），所有流量经反向代理到达。
- 不使用 80/443；不开放 FastAPI 端口、WebSocket 端口到公网。
- 使用独立 Docker 网络，与现有容器网络隔离。

## 2. 认证与授权

### 2.1 管理后台鉴权（已决策：应用内鉴权）

- 独立管理员认证机制，不复用现有 Caddy Basic Auth。
- 登录成功后签发 **JWT access token（约 15 分钟）+ refresh token（约 7 天）**，均写入 **HttpOnly + Secure + SameSite=Strict** Cookie，前端 JS 无法读取。
- 密码使用 **argon2id**（不可用 MD5/SHA 等快哈希）存储于 `admins.password_hash`。
- 状态变更接口需 **CSRF 防护**：`SameSite=Strict` 基础上再要求 `X-CSRF-Token`（double-submit）。
- **XSS 防护**：设置 CSP 响应头；token 不落 `localStorage`/`sessionStorage`；渲染层转义。
- 任何接口**不回显明文密钥/密码**，Provider Key 与 Agent secret 只返回掩码。

### 2.2 Windows Local Agent 凭据（已决策）

- 每个 Agent：唯一 `agent_id`（UUID4）+ 独立 `agent_secret`（256 位随机，base64url）。
- `agent_secret` **注册/轮换时仅返回一次**，服务端只存 `secret_hash`（argon2id），不存明文。
- WebSocket 握手必须鉴权（`X-Agent-Id` + `Authorization: Bearer`），未鉴权不进业务。
- 支持**轮换**（`secret_version` 递增 + 宽限期）与**吊销**（`revoked_at`，断开并拒绝重连）。
- 日志只记 `agent_id` 与凭据掩码，**禁止记录完整 secret**。

### 2.3 AI Provider 凭据

- 不写入镜像、不写入代码、不落日志。
- 因调用上游需要，`api_key` 以 **AES-GCM 加密存储**（主密钥来自 `config/`，权限 600）；前端仅见掩码。
- 与 Agent secret 区别：secret 用于「认证」→ 哈希；API Key 用于「调用」→ 加密。

## 3. 密钥管理

- SSH 密钥、面板密码、Agent token、AI Provider key 等均不入库、不入镜像层。
- 服务端密钥存放在 `/opt/ai-job-assistant/config/`，宿主权限 `600`。
- 现有密钥位置（用户环境）仅作参考，不在文档中明文记录。

## 4. 传输安全

- 公网链路全程 HTTPS/WSS，由 Caddy 终止 TLS（现有 8443 证书）。
- 内网（Caddy → FastAPI）走 `127.0.0.1` 回环，可选用 HTTP；如涉及敏感转发再评估 TLS。

## 5. 最小权限与隔离

- 容器以非 root 用户运行（如可行）。
- 只读挂载 `config/`，仅 `data/`、`logs/` 可写。
- CPU / 内存设置上限，防止资源耗尽影响现有业务。

## 6. 日志与审计

- 日志不记录密钥、token、AI Provider key 等敏感信息。
- 日志轮转（`max-size` / `max-file`）控制磁盘占用。

## 7. 变更纪律

- 不修改现有 Caddy 配置、现有容器、现有网络，除非经用户确认。
- 不执行 reboot / shutdown / 内核更新 / 系统升级，除非经用户确认。
