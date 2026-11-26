import type {
  AdminUser,
  AgentItem,
  AgentSecret,
  ApiEnvelope,
  AuditLogItem,
  CreateProviderInput,
  CreateTaskInput,
  PagedResult,
  ProviderItem,
  TaskItem,
  UpdateProviderInput,
} from "./types";

const MUTATING_METHODS = new Set(["POST", "PATCH", "PUT", "DELETE"]);
const IDEMPOTENT_METHODS = new Set(["GET", "HEAD"]);

export class ApiError extends Error {
  status: number;
  code: number;

  constructor(message: string, status: number, code: number) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function safeDecode(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

function readCookie(name: string): string | null {
  const cookies = document.cookie ? document.cookie.split("; ") : [];
  for (const item of cookies) {
    const idx = item.indexOf("=");
    if (idx === -1) continue;
    const key = safeDecode(item.slice(0, idx));
    if (key === name) {
      return safeDecode(item.slice(idx + 1));
    }
  }
  return null;
}

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const resp = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "include",
      });
      return resp.ok;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  allowRetry = true,
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (MUTATING_METHODS.has(method) && path !== "/api/auth/login") {
    const csrf = readCookie("csrf_token");
    if (csrf) {
      headers.set("X-CSRF-Token", csrf);
    }
  }

  const resp = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: "include",
  });

  if (
    resp.status === 401 &&
    allowRetry &&
    path !== "/api/auth/login" &&
    path !== "/api/auth/refresh"
  ) {
    const refreshed = await tryRefreshSession();
    if (refreshed && IDEMPOTENT_METHODS.has(method)) {
      return request<T>(path, options, false);
    }
  }

  if (resp.status === 204 || resp.status === 205) {
    return undefined as T;
  }

  let body: ApiEnvelope<T> | null = null;
  try {
    body = (await resp.json()) as ApiEnvelope<T>;
  } catch {
    body = null;
  }

  if (!resp.ok || !body || body.code !== 0) {
    throw new ApiError(
      body?.message || `请求失败（HTTP ${resp.status}）`,
      resp.status,
      body?.code ?? resp.status,
    );
  }
  return body.data;
}

export const api = {
  login(username: string, password: string) {
    return request<{ username: string; csrf_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },
  me() {
    return request<AdminUser>("/api/auth/me");
  },
  logout() {
    return request<null>("/api/auth/logout", { method: "POST" });
  },
  listAgents() {
    return request<PagedResult<AgentItem>>("/api/agents?limit=200");
  },
  registerAgent(name: string) {
    return request<AgentSecret>("/api/agents", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  },
  rotateAgentSecret(agentId: string) {
    return request<AgentSecret>(`/api/agents/${encodeURIComponent(agentId)}/rotate-secret`, {
      method: "POST",
    });
  },
  revokeAgent(agentId: string) {
    return request<AgentItem>(`/api/agents/${encodeURIComponent(agentId)}/revoke`, {
      method: "POST",
    });
  },
  deleteAgent(agentId: string) {
    return request<null>(`/api/agents/${encodeURIComponent(agentId)}`, {
      method: "DELETE",
    });
  },
  listTasks(status?: string) {
    const query = status && status !== "all" ? `?status=${encodeURIComponent(status)}&limit=100` : "?limit=100";
    return request<PagedResult<TaskItem>>(`/api/tasks${query}`);
  },
  createTask(input: CreateTaskInput) {
    return request<TaskItem>("/api/tasks", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  cancelTask(taskId: string) {
    return request<{ task_id: string; status: string; attempt: number }>(
      `/api/tasks/${encodeURIComponent(taskId)}/cancel`,
      { method: "POST" },
    );
  },
  listProviders() {
    return request<PagedResult<ProviderItem>>("/api/providers?limit=200");
  },
  createProvider(input: CreateProviderInput) {
    return request<ProviderItem>("/api/providers", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  updateProvider(providerId: number, input: UpdateProviderInput) {
    return request<ProviderItem>(`/api/providers/${providerId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },
  deleteProvider(providerId: number) {
    return request<null>(`/api/providers/${providerId}`, {
      method: "DELETE",
    });
  },
  listAuditLogs(action?: string) {
    const query =
      action && action !== "all"
        ? `?action=${encodeURIComponent(action)}&limit=100`
        : "?limit=100";
    return request<PagedResult<AuditLogItem>>(`/api/audit-logs${query}`);
  },
};
