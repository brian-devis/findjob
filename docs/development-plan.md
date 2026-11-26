# AIJob 开发计划（P0）

> 当前处于 **P0 架构设计阶段**，仅更新架构与部署设计，不进入 P1。

## 1. 阶段划分

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P0 | 架构设计、部署设计、安全设计、开发计划、README | 进行中 |
| P1 | 现场环境复检、Caddy 接入方案确认、Compose 定稿、基础 FastAPI + 静态托管 + SQLite | 未开始 |
| P2 | Agent Manager / Task Manager / AI Provider、Windows Local Agent、管理后台完整功能 | 未开始 |

## 2. P0 产出

- `README.md`
- `AGENTS.md`
- `.gitignore`
- `docs/architecture.md`
- `docs/deployment.md`
- `docs/security.md`
- `docs/database.md`
- `docs/websocket-protocol.md`
- `docs/api.md`
- `docs/development-plan.md`

## 3. P0 边界（禁止事项）

- 不 SSH 登录服务器。
- 不修改 Caddy。
- 不创建服务器目录。
- 不创建 Docker 容器。
- 不执行服务器部署。
- 不重启服务器。
- 不进入 P1。

## 4. 进入 P1 的前提

1. 用户确认 P0 文档。
2. 完成现场环境复检（CPU/内存/磁盘、容器、网络、端口、Caddy 配置、证书与代理规则）。
3. 用户确认 8443 接入方案（路径 / 子域名）。

## 5. 架构决策状态

- [x] 8443 接入方案：独立子域名 `fj.asgo.click`（已确认）。
- [x] 端口规划：容器内 8000，宿主 `127.0.0.1:8100`（候选，P1 复核未占用）。
- [x] 管理后台鉴权：应用内鉴权（JWT HttpOnly Cookie + argon2id + CSRF/XSS）。
- [x] Agent 凭据：UUID4 + 独立 secret（哈希存储、轮换、吊销、WS 握手鉴权）。
- [x] 静态资源：React 构建由 FastAPI 托管，不引入 Nginx 容器。

## 6. 架构一致性审查

见 `docs/architecture.md` 与本文档末尾的验收结论；重点检查项：任务状态机完整性、WebSocket 断线恢复、Agent 重连去重、SQLite 并发、鉴权完整性、端口/网络冲突、8443 反代冲突、CPU/内存限制。

## 7. P0 遗留 / 待 P1 现场确认

- [ ] 回环端口 `8100` 是否真的空闲（P1 `ss -lntp` 复核）。
- [ ] 现有 Caddyfile / 证书 / 代理规则现场复检，确认 `fj.asgo.click` 无冲突。
- [ ] Agent 本地「task_id 执行记录」是否落盘（影响断线去重可靠性）。
- [ ] SQLite 是否需按需切换为 PostgreSQL（当前规模不需要，观察）。
- [ ] 前端/后端技术栈细节、依赖版本锁定（P1 定稿）。
