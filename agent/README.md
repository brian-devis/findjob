# AIJob Local Agent

运行在用户 Windows（或 Linux）本机的轻量级客户端，通过 WSS 接入中心服务，并在本机可见浏览器中执行 **BOSS 直聘** 相关操作。

## 特性

- **握手鉴权**：携带 `X-Agent-Id` 与 `Authorization: Bearer <agent_secret>`；日志仅打印脱敏掩码。
- **心跳保活与自动重连**：应用层 `ping`/`pong`，断线后指数退避 + 抖动重连（鉴权失败/吊销 `4001`/`4002` 不重试）。
- **本地持久化幂等**：执行结果写入本地 SQLite WAL（`data/agent_state.db`），同一 `task_id` 不重复执行；断线未送达的结果在重连后自动补报。
- **基础与 BOSS 执行器**：
  - 基础连通性：`PING`、`SYSTEM_INFO`（支持超时与 `task_cancel` 取消）；
  - BOSS 业务执行器：`BOSS_CHECK_LOGIN`（登录态检测）、`BOSS_SYNC_RESUME`（个人优势同步，支持 `dry_run`）、`BOSS_SCAN_JOBS`（岗位卡片扫描采集）、`BOSS_APPLY_JOB`（沟通去重与打招呼投递，支持 `dry_run`）。
- **本地持久化浏览器与合规边界**：
  - 通过 Playwright 启动本机可见桌面 Chrome / Edge（默认 `AIJOB_BROWSER_HEADLESS=false`、`AIJOB_BROWSER_CHANNEL=chrome`），使用独立持久化目录复用登录态（首次在管理后台触发「检查 BOSS 登录态」或打开浏览器窗口扫码登录即可）；
  - **绝不绕过平台风控**：遇到未登录、短信验证或滑块/人机验证时立即停止当前自动化并返回 `needs_human_action=true`，提示用户在本地浏览器窗口手动完成后重试。

## Windows 一键启动

```powershell
cd agent
.\start-windows.ps1
```

首次运行若未检测到 `.env`，脚本会自动从 `.env.example` 复制并提示填入在管理后台注册 Agent 后获得的一次性凭据；同时默认将浏览器持久化目录设置到 `%LOCALAPPDATA%\AIJob\browser-profile`（若 `.env` 未显式指定）。

## 手动启动

```bash
cd agent
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填入注册 Agent 时获得的 agent_id 和 secret
python -m agent.main
```
