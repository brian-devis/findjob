import { useState } from "react";
import { ApiError } from "../api";
import type { AuditLogItem } from "../types";

interface Props {
  logs: AuditLogItem[];
  actionFilter: string;
  onActionFilterChange: (action: string) => void;
  onRefresh: () => Promise<void>;
}

const ACTION_OPTIONS = [
  "all",
  "auth.login",
  "auth.logout",
  "agent.register",
  "agent.rotate_secret",
  "agent.revoke",
  "agent.delete",
  "agent.check_boss_login",
  "task.create",
  "task.cancel",
  "provider.create",
  "provider.update",
  "provider.delete",
  "resume.create",
  "resume.upload",
  "resume.update",
  "resume.activate",
  "resume.delete",
  "resume.ai_review",
  "resume.ai_rewrite",
  "resume.sync_boss",
  "job.preference_update",
  "job.import",
  "job.scan",
  "job.ai_score",
  "job.ai_score_batch",
  "job.apply",
  "job.skip",
  "job.restore",
  "job.auto_apply",
];

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function AuditPanel({
  logs,
  actionFilter,
  onActionFilterChange,
  onRefresh,
}: Props) {
  const [error, setError] = useState<string | null>(null);

  async function safeRefresh() {
    setError(null);
    try {
      await onRefresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "刷新审计日志失败");
    }
  }

  return (
    <div className="stack">
      {error && <div className="alert alert-error">{error}</div>}
      <section className="card">
        <div className="section-head">
          <h2>审计日志（{logs.length}）</h2>
          <div className="toolbar">
            <select
              value={actionFilter}
              onChange={(e) => onActionFilterChange(e.target.value)}
            >
              {ACTION_OPTIONS.map((act) => (
                <option key={act} value={act}>
                  {act === "all" ? "全部操作" : act}
                </option>
              ))}
            </select>
            <button className="btn btn-ghost" type="button" onClick={() => void safeRefresh()}>
              刷新
            </button>
          </div>
        </div>

        {logs.length === 0 ? (
          <p className="empty">暂无审计记录</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>操作者</th>
                  <th>动作</th>
                  <th>对象</th>
                  <th>摘要详情</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((item) => (
                  <tr key={item.id}>
                    <td>{formatTime(item.ts)}</td>
                    <td className="mono">{item.actor}</td>
                    <td>
                      <span className="pill pill-blue">{item.action}</span>
                    </td>
                    <td className="mono">{item.target}</td>
                    <td className="mono">
                      {item.detail && Object.keys(item.detail).length > 0
                        ? JSON.stringify(item.detail)
                        : "—"}
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
