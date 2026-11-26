import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { AgentsPanel } from "./components/AgentsPanel";
import { AuditPanel } from "./components/AuditPanel";
import { LoginView } from "./components/LoginView";
import { ProvidersPanel } from "./components/ProvidersPanel";
import { TasksPanel } from "./components/TasksPanel";
import type { AgentItem, AuditLogItem, ProviderItem, TaskItem } from "./types";

type Tab = "agents" | "tasks" | "providers" | "audit";

export function App() {
  const [checking, setChecking] = useState(true);
  const [username, setUsername] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("agents");
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [providers, setProviders] = useState<ProviderItem[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [auditActionFilter, setAuditActionFilter] = useState("all");

  const loadData = useCallback(async () => {
    const [agentRes, taskRes, providerRes, auditRes] = await Promise.all([
      api.listAgents(),
      api.listTasks(statusFilter),
      api.listProviders(),
      api.listAuditLogs(auditActionFilter),
    ]);
    setAgents(agentRes.items);
    setTasks(taskRes.items);
    setProviders(providerRes.items);
    setAuditLogs(auditRes.items);
  }, [statusFilter, auditActionFilter]);

  useEffect(() => {
    void (async () => {
      try {
        const me = await api.me();
        setUsername(me.username);
      } catch {
        setUsername(null);
      } finally {
        setChecking(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!username) return;
    void loadData().catch(() => undefined);
    const timer = window.setInterval(() => {
      void loadData().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [username, loadData]);

  async function handleLogout() {
    try {
      await api.logout();
    } finally {
      setUsername(null);
      setAgents([]);
      setTasks([]);
      setProviders([]);
      setAuditLogs([]);
    }
  }

  if (checking) {
    return <div className="loading-screen">正在加载 AIJob 管理后台...</div>;
  }

  if (!username) {
    return <LoginView onSuccess={(user) => setUsername(user)} />;
  }

  const onlineCount = agents.filter((a) => a.online).length;
  const activeTaskCount = tasks.filter(
    (t) => t.status === "queued" || t.status === "dispatched" || t.status === "running",
  ).length;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-left">
          <span className="brand-badge">AIJob</span>
          <nav className="tabs">
            <button
              className={`tab ${tab === "agents" ? "tab-active" : ""}`}
              type="button"
              onClick={() => setTab("agents")}
            >
              Agents ({onlineCount}/{agents.length})
            </button>
            <button
              className={`tab ${tab === "tasks" ? "tab-active" : ""}`}
              type="button"
              onClick={() => setTab("tasks")}
            >
              任务队列 ({activeTaskCount} 进行中)
            </button>
            <button
              className={`tab ${tab === "providers" ? "tab-active" : ""}`}
              type="button"
              onClick={() => setTab("providers")}
            >
              AI Providers ({providers.length})
            </button>
            <button
              className={`tab ${tab === "audit" ? "tab-active" : ""}`}
              type="button"
              onClick={() => setTab("audit")}
            >
              审计日志 ({auditLogs.length})
            </button>
          </nav>
        </div>
        <div className="topbar-right">
          <span className="muted">管理员：{username}</span>
          <button className="btn btn-ghost" type="button" onClick={() => void handleLogout()}>
            退出登录
          </button>
        </div>
      </header>

      <main className="container">
        {tab === "agents" && <AgentsPanel agents={agents} onRefresh={loadData} />}
        {tab === "tasks" && (
          <TasksPanel
            agents={agents}
            tasks={tasks}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            onRefresh={loadData}
          />
        )}
        {tab === "providers" && (
          <ProvidersPanel providers={providers} onRefresh={loadData} />
        )}
        {tab === "audit" && (
          <AuditPanel
            logs={auditLogs}
            actionFilter={auditActionFilter}
            onActionFilterChange={setAuditActionFilter}
            onRefresh={loadData}
          />
        )}
      </main>
    </div>
  );
}
