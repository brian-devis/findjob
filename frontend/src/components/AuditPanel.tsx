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
  "task.create",
  "task.cancel",
  "provider.create",
  "provider.update",
  "provider.delete",
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
  return (
    <div className="stack">
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
            <button className="btn btn-ghost" type="button" onClick={() => void onRefresh()}>
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
                      {Object.keys(item.detail).length > 0
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
