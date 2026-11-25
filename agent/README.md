# AIJob Local Agent

运行在用户 Windows（或 Linux）本机的轻量级客户端，通过 WSS/HTTPS 与中心服务通信。

## 特性

- **握手鉴权**：携带 `X-Agent-Id` 与 `Authorization: Bearer <agent_secret>`；日志仅打印脱敏掩码。
- **心跳保活与自动重连**：应用层 `ping`/`pong`，断线后指数退避 + 抖动重连（鉴权失败/吊销 `4001`/`4002` 不重试）。
- **本地持久化幂等**：执行结果写入本地 SQLite WAL（`data/agent_state.db`），同一 `task_id` 不重复执行；断线未送达的结果在重连后自动补报。
- **内置执行器**：`PING`、`SYSTEM_INFO`（零第三方系统监控依赖，支持超时与 `task_cancel` 取消）。

## 快速启动

```bash
cd agent
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填入注册 Agent 时获得的 agent_id 和 secret
python -m agent.main
```
