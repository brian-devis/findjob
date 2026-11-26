import { FormEvent, useState } from "react";
import { api, ApiError } from "../api";
import type { AgentItem, TaskItem, TaskType } from "../types";

interface Props {
  agents: AgentItem[];
  tasks: TaskItem[];
  statusFilter: string;
  onStatusFilterChange: (status: string) => void;
  onRefresh: () => Promise<void>;
}

const STATUS_OPTIONS = [
  "all",
  "queued",
  "dispatched",
  "running",
  "succeeded",
  "failed",
  "cancelled",
];

function statusClass(status: string): string {
  switch (status) {
    case "succeeded":
      return "pill-green";
    case "running":
    case "dispatched":
      return "pill-blue";
    case "failed":
      return "pill-red";
    case "cancelled":
      return "pill-gray";
    default:
      return "pill-amber";
  }
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function TasksPanel({
  agents,
  tasks,
  statusFilter,
  onStatusFilterChange,
  onRefresh,
}: Props) {
  const [taskType, setTaskType] = useState<TaskType>("PING");
  const [agentId, setAgentId] = useState<string>("");
  const [priority, setPriority] = useState(0);
  const [maxAttempts, setMaxAttempts] = useState(1);
  const [timeoutSeconds, setTimeoutSeconds] = useState(60);
  const [payloadText, setPayloadText] = useState('{"echo": "hello"}');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  const activeAgents = agents.filter((a) => a.status === "active");
  const selectedTask = selectedTaskId
    ? tasks.find((t) => t.task_id === selectedTaskId) ?? null
    : null;

  async function safeRefresh() {
    setError(null);
    try {
      await onRefresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "刷新任务列表失败");
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    let parsedPayload: Record<string, unknown>;
    try {
      const raw = JSON.parse(payloadText || "{}");
      if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
        throw new Error("Payload 必须是 JSON 对象");
      }
      parsedPayload = raw as Record<string, unknown>;
    } catch (err) {
      setError(err instanceof Error ? `Payload 格式错误：${err.message}` : "Payload 格式错误");
      return;
    }

    setBusy(true);
    try {
      await api.createTask({
        type: taskType,
        agent_id: agentId || null,
        payload: parsedPayload,
        priority,
        max_attempts: maxAttempts,
        timeout_seconds: timeoutSeconds,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建任务失败");
      setBusy(false);
      return;
    }
    try {
      await onRefresh();
    } catch {
      setError("任务已创建，但刷新列表失败，请点击刷新重试");
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel(taskId: string) {
    setError(null);
    setBusy(true);
    try {
      await api.cancelTask(taskId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "取消任务失败");
      setBusy(false);
      return;
    }
    try {
      await onRefresh();
    } catch {
      setError("取消请求已成功，但刷新列表失败，请点击刷新重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <section className="card">
        <div className="section-head">
          <h2>创建任务</h2>
          <span className="muted">不指定 Agent 时将由调度器自动分配给在线 Agent</span>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        <form className="task-form" onSubmit={handleCreate}>
          <div className="form-grid">
            <label className="field">
              <span>任务类型</span>
              <select
                value={taskType}
                onChange={(e) => setTaskType(e.target.value as TaskType)}
              >
                <option value="PING">PING</option>
                <option value="SYSTEM_INFO">SYSTEM_INFO</option>
                <option value="BOSS_CHECK_LOGIN">BOSS_CHECK_LOGIN</option>
                <option value="BOSS_SYNC_RESUME">BOSS_SYNC_RESUME</option>
                <option value="BOSS_SCAN_JOBS">BOSS_SCAN_JOBS</option>
                <option value="BOSS_APPLY_JOB">BOSS_APPLY_JOB</option>
              </select>
            </label>

            <label className="field">
              <span>目标 Agent</span>
              <select value={agentId} onChange={(e) => setAgentId(e.target.value)}>
                <option value="">自动分配（任意在线 Agent）</option>
                {activeAgents.map((a) => (
                  <option key={a.agent_id} value={a.agent_id}>
                    {a.name} ({a.online ? "在线" : "离线"})
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>优先级</span>
              <input
                type="number"
                min={0}
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
              />
            </label>

            <label className="field">
              <span>最大重试次数</span>
              <input
                type="number"
                min={1}
                max={10}
                value={maxAttempts}
                onChange={(e) => setMaxAttempts(Number(e.target.value))}
              />
            </label>

            <label className="field">
              <span>超时（秒）</span>
              <input
                type="number"
                min={1}
                max={86400}
                value={timeoutSeconds}
                onChange={(e) => setTimeoutSeconds(Number(e.target.value))}
              />
            </label>
          </div>

          <label className="field">
            <span>Payload（JSON）</span>
            <textarea
              rows={2}
              className="mono"
              value={payloadText}
              onChange={(e) => setPayloadText(e.target.value)}
            />
          </label>

          <div>
            <button className="btn btn-primary" type="submit" disabled={busy}>
              下发任务
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="section-head">
          <h2>任务列表（{tasks.length}）</h2>
          <div className="toolbar">
            <select
              value={statusFilter}
              onChange={(e) => onStatusFilterChange(e.target.value)}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s === "all" ? "全部状态" : s}
                </option>
              ))}
            </select>
            <button className="btn btn-ghost" type="button" onClick={() => void safeRefresh()}>
              刷新
            </button>
          </div>
        </div>

        {tasks.length === 0 ? (
          <p className="empty">暂无符合条件的任务</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>类型</th>
                  <th>状态</th>
                  <th>Task ID</th>
                  <th>目标 Agent</th>
                  <th>重试</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t) => {
                  const cancellable =
                    t.status === "queued" || t.status === "dispatched" || t.status === "running";
                  return (
                    <tr key={t.task_id}>
                      <td><strong>{t.type}</strong></td>
                      <td>
                        <span className={`pill ${statusClass(t.status)}`}>{t.status}</span>
                      </td>
                      <td className="mono">{t.task_id.slice(0, 8)}…</td>
                      <td className="mono">{t.agent_id ? `${t.agent_id.slice(0, 8)}…` : "未分配"}</td>
                      <td>
                        {t.attempt}/{t.max_attempts}
                      </td>
                      <td>{formatTime(t.created_at)}</td>
                      <td className="actions">
                        <button
                          className="btn btn-sm btn-secondary"
                          type="button"
                          onClick={() => setSelectedTaskId(t.task_id)}
                        >
                          详情
                        </button>
                        {cancellable && (
                          <button
                            className="btn btn-sm btn-danger"
                            type="button"
                            disabled={busy}
                            onClick={() => void handleCancel(t.task_id)}
                          >
                            取消
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selectedTask && (
        <section className="card">
          <div className="section-head">
            <h3>任务详情：{selectedTask.task_id}</h3>
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() => setSelectedTaskId(null)}
            >
              关闭
            </button>
          </div>
          <div className="detail-grid">
            <div><span className="muted">状态：</span>{selectedTask.status}</div>
            <div><span className="muted">类型：</span>{selectedTask.type}</div>
            <div><span className="muted">分发时间：</span>{formatTime(selectedTask.dispatched_at)}</div>
            <div><span className="muted">开始时间：</span>{formatTime(selectedTask.started_at)}</div>
            <div><span className="muted">完成时间：</span>{formatTime(selectedTask.finished_at)}</div>
            <div><span className="muted">错误信息：</span>{selectedTask.error || "无"}</div>
          </div>
          {Boolean(
            (selectedTask.result as Record<string, unknown> | null)?.needs_human_action,
          ) && (
            <div className="alert alert-warning">
              <strong>需要本地人工操作：</strong>
              {String(
                (selectedTask.result as Record<string, unknown>).message ??
                  "请在 Local Agent 打开的桌面浏览器中完成扫码登录或安全验证后重试",
              )}
            </div>
          )}
          <p className="muted">Payload</p>
          <pre className="code-block">{JSON.stringify(selectedTask.payload, null, 2)}</pre>
          <p className="muted">Result</p>
          <pre className="code-block">
            {selectedTask.result !== null ? JSON.stringify(selectedTask.result, null, 2) : "—"}
          </pre>
        </section>
      )}
    </div>
  );
}
