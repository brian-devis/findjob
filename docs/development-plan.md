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
- `docs/architecture.md`
- `docs/deployment.md`
- `docs/security.md`
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

## 5. 待确认事项（P0 遗留）

- [x] 8443 接入方案：独立子域名 `fj.asgo.click`（已确认）。
- [ ] 服务端回环监听端口（避开 7863 / 7864 等现有端口）。
- [ ] 管理后台鉴权方式（Caddy Basic Auth vs 应用内鉴权）。
- [ ] Windows Local Agent 的认证凭据方案。
- [ ] 是否由 FastAPI 统一托管 React 静态资源（初步建议：是）。
