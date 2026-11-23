# AIJob 安全设计（P0）

> 阶段：P0 架构设计。本文档定义安全原则与边界，具体实现于 P1 落地。

## 1. 网络边界

- AIJob 服务**只监听 `127.0.0.1`**，不向公网暴露任何端口。
- 公网唯一入口为现有 Caddy（8443），所有流量经反向代理到达。
- 不使用 80/443；不开放 FastAPI 端口、WebSocket 端口到公网。
- 使用独立 Docker 网络，与现有容器网络隔离。

## 2. 认证与授权

- **管理后台**：通过 Caddy 层 Basic Auth（复用现有面板密码机制）或应用内鉴权；未确认前不裸奔。
- **Windows Local Agent**：Agent 注册与连接必须携带独立凭据（token / 密钥），由 Agent Manager 校验。
- **AI Provider 凭据**：不写入镜像、不写入代码，只存于 `config/`（权限 600）或环境变量（.env 不入库）。

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
