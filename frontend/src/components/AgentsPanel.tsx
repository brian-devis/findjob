import { FormEvent, useState } from "react";
import { api, ApiError } from "../api";
import type { AgentItem, AgentSecret, TaskItem } from "../types";

interface Props {
  agents: AgentItem[];
  tasks: TaskItem[];
  onRefresh: () => Promise<void>;
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function AgentsPanel({ agents, tasks, onRefresh }: Props) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [oneTimeSecret, setOneTimeSecret] = useState<AgentSecret | null>(null);
  const [copied, setCopied] = useState(false);

  const latestBossCheck = tasks.find((t) => t.type === "BOSS_CHECK_LOGIN") ?? null;
  const checkResult = latestBossCheck?.result as Record<string, unknown> | null | undefined;

  async function safeRefresh() {
    setError(null);
    try {
      await onRefresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "刷新 Agent 列表失败");
    }
  }

  async function handleRegister(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const secret = await api.registerAgent(name.trim());
      setOneTimeSecret(secret);
      setCopied(false);
      setName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "注册 Agent 失败");
      setBusy(false);
      return;
    }
    try {
      await onRefresh();
    } catch {
      setError("操作已成功，但刷新列表失败，请点击刷新重试");
    } finally {
      setBusy(false);
    }
  }

  async function handleRotate(agentId: string) {
    setError(null);
    setBusy(true);
    try {
      const secret = await api.rotateAgentSecret(agentId);
      setOneTimeSecret(secret);
      setCopied(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "轮换凭据失败");
      setBusy(false);
      return;
    }
    try {
      await onRefresh();
    } catch {
      setError("操作已成功，但刷新列表失败，请点击刷新重试");
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(agentId: string, agentName: string) {
    if (!window.confirm(`确认吊销 Agent「${agentName}」？在线连接将立即断开且无法重连。`)) {
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await api.revokeAgent(agentId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "吊销失败");
      setBusy(false);
      return;
    }
    try {
      await onRefresh();
    } catch {
      setError("吊销已成功，但刷新列表失败，请点击刷新重试");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(agentId: string, agentName: string) {
    if (!window.confirm(`确认永久删除 Agent「${agentName}」？`)) {
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await api.deleteAgent(agentId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
      setBusy(false);
      return;
    }
    try {
      await onRefresh();
    } catch {
      setError("删除已成功，但刷新列表失败，请点击刷新重试");
    } finally {
      setBusy(false);
    }
  }

  async function handleCheckBossLogin(agentId: string, agentName: string) {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const task = await api.checkBossLogin(agentId);
      setNotice(`已向「${agentName}」下发 BOSS 登录态检测任务（${task.task_id.slice(0, 8)}）`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "下发 BOSS 登录检测失败");
      setBusy(false);
      return;
    }
    try {
      await onRefresh();
    } catch {
      setError("任务已下发，但刷新列表失败，请点击刷新重试");
    } finally {
      setBusy(false);
    }
  }

  async function copySecret() {
    if (!oneTimeSecret) return;
    try {
      await navigator.clipboard.writeText(
        `AIJOB_AGENT_ID=${oneTimeSecret.agent_id}\nAIJOB_AGENT_SECRET=${oneTimeSecret.secret}`,
      );
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="stack">
      <section className="card">
        <div className="section-head">
          <h2>注册新 Agent</h2>
          <span className="muted">注册后将一次性返回凭据，服务端仅存哈希</span>
        </div>
        <form className="inline-form" onSubmit={handleRegister}>
          <input
            type="text"
            placeholder="输入 Agent 名称（例如 win-desktop-01）"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={128}
            required
          />
          <button className="btn btn-primary" type="submit" disabled={busy}>
            注册 Agent
          </button>
        </form>
      </section>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-success">{notice}</div>}

      {latestBossCheck && (
        <div
          className={`alert ${
            checkResult?.needs_human_action
              ? "alert-warning"
              : latestBossCheck.status === "succeeded" && checkResult?.logged_in
                ? "alert-success"
                : latestBossCheck.status === "failed"
                  ? "alert-error"
                  : "alert-warning"
          }`}
        >
          <strong>最近 BOSS 登录态检测（{latestBossCheck.status}）：</strong>
          {typeof checkResult?.message === "string"
            ? checkResult.message
            : latestBossCheck.error || "等待本地 Agent 执行完成，请留意本地 Chrome/Edge 浏览器窗口"}
        </div>
      )}

      {oneTimeSecret && (
        <section className="card secret-banner">
          <div className="section-head">
            <h3>一次性 Agent 凭据（请立即保存）</h3>
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() => setOneTimeSecret(null)}
            >
              我已保存，关闭
            </button>
          </div>
          <p className="muted">关闭后将无法再次查看明文 secret，请写入 Local Agent 的 .env 文件：</p>
          <pre className="code-block">
{`AIJOB_AGENT_ID=${oneTimeSecret.agent_id}
AIJOB_AGENT_SECRET=${oneTimeSecret.secret}`}
          </pre>
          <button className="btn btn-secondary" type="button" onClick={copySecret}>
            {copied ? "已复制到剪贴板" : "复制 .env 配置片段"}
          </button>
        </section>
      )}

      <section className="card">
        <div className="section-head">
          <h2>Agent 列表（{agents.length}）</h2>
          <button className="btn btn-ghost" type="button" onClick={() => void safeRefresh()}>
            刷新
          </button>
        </div>

        {agents.length === 0 ? (
          <p className="empty">暂无已注册的 Agent</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>连接</th>
                  <th>状态</th>
                  <th>Agent ID</th>
                  <th>凭据版本</th>
                  <th>最近心跳</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.agent_id}>
                    <td><strong>{a.name}</strong></td>
                    <td>
                      <span className={`pill ${a.online ? "pill-green" : "pill-gray"}`}>
                        {a.online ? "在线" : "离线"}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`pill ${a.status === "active" ? "pill-blue" : "pill-red"}`}
                      >
                        {a.status}
                      </span>
                    </td>
                    <td className="mono">{a.agent_id}</td>
                    <td>v{a.secret_version}</td>
                    <td>{formatTime(a.last_seen_at)}</td>
                    <td className="actions">
                      {a.status === "active" && (
                        <>
                          <button
                            className="btn btn-sm btn-primary"
                            type="button"
                            disabled={busy}
                            onClick={() => void handleCheckBossLogin(a.agent_id, a.name)}
                          >
                            检查 BOSS 登录态
                          </button>
                          <button
                            className="btn btn-sm btn-secondary"
                            type="button"
                            disabled={busy}
                            onClick={() => void handleRotate(a.agent_id)}
                          >
                            轮换密钥
                          </button>
                          <button
                            className="btn btn-sm btn-warning"
                            type="button"
                            disabled={busy}
                            onClick={() => void handleRevoke(a.agent_id, a.name)}
                          >
                            吊销
                          </button>
                        </>
                      )}
                      <button
                        className="btn btn-sm btn-danger"
                        type="button"
                        disabled={busy}
                        onClick={() => void handleDelete(a.agent_id, a.name)}
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
