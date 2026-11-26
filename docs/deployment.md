# AIJob 部署设计（P0）

> 阶段：P0 架构设计。本文档是部署**设计**，尚未在服务器上执行任何变更。

## 1. 部署原则

1. 独立 Docker Compose 项目，项目名 `ai-job-assistant`。
2. 不删除 / 不停止 / 不修改现有容器与网络。
3. 不占用现有端口；不使用 80/443。
4. FastAPI 与管理后台不直接暴露公网，仅监听 `127.0.0.1`。
5. 公网通过现有 Caddy 的 8443 入口接入，需先规划路径/子域名并经确认。
6. 不执行 reboot / shutdown / 内核更新 / 系统升级。

## 2. 宿主目录规划

```
/opt/ai-job-assistant/
├── data/      # SQLite（持久卷，容器重建不丢）
├── logs/      # 日志（json-file 或挂载卷）
├── config/    # 应用配置与密钥（权限 600）
└── deploy/    # docker-compose.yml、.env 等
```

## 3. 资源规划（初步）

| 服务 | CPU 上限 | 内存上限 |
| --- | --- | --- |
| FastAPI（含静态资源托管） | 0.75 核 | 512 MiB |
| Web 静态资源（若独立部署） | 0.25 核 | 128 MiB |

> 优先由 FastAPI 托管 React 构建产物，减少独立容器。实际部署前结合 Docker 当前资源占用再次评估。

## 4. Compose 结构（草案，P1 再定稿）

```yaml
name: ai-job-assistant            # 独立 Compose 项目名
services:
  backend:                        # FastAPI + 静态资源
    ports:
      - "127.0.0.1:8100:8000"     # 仅本机回环；候选 8100，P1 现场复核未占用（避开 7863/7864 等）
    volumes:
      - /opt/ai-job-assistant/data:/data
      - /opt/ai-job-assistant/logs:/logs
      - /opt/ai-job-assistant/config:/config:ro
    deploy:
      resources:
        limits:
          cpus: "0.75"
          memory: "512M"
networks:
  default:
    driver: bridge                # 独立网络，不 join 现有网络
```

> 上述为草案，具体端口、镜像、健康检查等在 P1 依据现场复检结果定稿。

## 5. 公网接入方案

因 80/443 被拦截、现有 8443 已承载 `api.asgo.click` 与 `panel.asgo.click`，AIJob 需复用 8443 入口。**必须先现场检查 Caddyfile、监听端口、反向代理规则与证书**，再提出并确认接入方案。

### 已确认接入方案

- **AIJob 独立子域名：`fj.asgo.click`（复用 8443 端口）**，与现有 `api.asgo.click` / `panel.asgo.click` 并存。
- 管理后台鉴权：**应用内鉴权**（已决策，非 Caddy Basic Auth），见 `security.md`。
- WebSocket 经同一 8443 入口反代（Caddy `reverse_proxy` 原生支持 WebSocket 升级），不额外开放端口。

> 虽然子域名已确定，但**实际写入 Caddyfile 前仍必须现场检查现有配置、证书与代理规则**，确认无冲突后再经用户确认执行。

## 6. 部署前检查清单（P1 执行前必须完成）

| 检查项 | 目的 |
| --- | --- |
| CPU / 内存 / 磁盘 | 确认资源余量支持新增服务 |
| `docker ps` / `docker network ls` | 确认现有容器、网络，避免冲突 |
| `ss -lntp` | 确认现有端口占用，选择未占用回环端口 |
| `/etc/caddy/Caddyfile` | 确认现有站点、代理规则、证书、监听端口 |
| 证书与域名解析 | 确认 asgo.click 域名与 8443 证书现状 |
| `systemctl list-units --failed` | 确认无失败单元 |
| `uname -r` / 待重启内核 | 确认内核状态，避免意外重启 |

## 7. 数据持久化与备份

- SQLite 文件位于 `/opt/ai-job-assistant/data/`，由命名卷或绑定挂载持久化。
- 容器使用 `restart: unless-stopped`，日志限制 `max-size` / `max-file`。
- 备份策略（P1 设计）：定期备份 `data/` 与 `config/`。
