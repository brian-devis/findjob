import type {
  AdminUser,
  AgentItem,
  AgentSecret,
  ApiEnvelope,
  AuditLogItem,
  BossJobItem,
  BossJobListData,
  CreateProviderInput,
  CreateResumeInput,
  CreateTaskInput,
  JobPreference,
  JobPreferenceUpdateInput,
  PagedResult,
  ProviderItem,
  ResumeDetail,
  ResumeSummary,
  TaskItem,
  UpdateProviderInput,
  UpdateResumeInput,
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
  const isFormData =
    typeof FormData !== "undefined" && options.body instanceof FormData;
  if (options.body !== undefined && !isFormData && !headers.has("Content-Type")) {
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
  checkBossLogin(agentId: string) {
    return request<TaskItem>(`/api/agents/${encodeURIComponent(agentId)}/check-boss-login`, {
      method: "POST",
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
  listResumes() {
    return request<PagedResult<ResumeSummary>>("/api/resumes?limit=100");
  },
  getResume(resumeId: number) {
    return request<ResumeDetail>(`/api/resumes/${resumeId}`);
  },
  createResume(input: CreateResumeInput) {
    return request<ResumeDetail>("/api/resumes", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  uploadResume(file: File, title?: string, targetRole?: string) {
    const form = new FormData();
    form.append("file", file);
    if (title?.trim()) form.append("title", title.trim());
    if (targetRole?.trim()) form.append("target_role", targetRole.trim());
    return request<ResumeDetail>("/api/resumes/upload", {
      method: "POST",
      body: form,
    });
  },
  updateResume(resumeId: number, input: UpdateResumeInput) {
    return request<ResumeDetail>(`/api/resumes/${resumeId}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },
  activateResume(resumeId: number) {
    return request<ResumeDetail>(`/api/resumes/${resumeId}/activate`, {
      method: "POST",
    });
  },
  deleteResume(resumeId: number) {
    return request<null>(`/api/resumes/${resumeId}`, {
      method: "DELETE",
    });
  },
  aiReviewResume(resumeId: number, providerId?: number, targetRole?: string) {
    return request<ResumeDetail>(`/api/resumes/${resumeId}/ai-review`, {
      method: "POST",
      body: JSON.stringify({
        provider_id: providerId ?? null,
        target_role: targetRole?.trim() || null,
      }),
    });
  },
  aiRewriteResume(
    resumeId: number,
    providerId?: number,
    targetRole?: string,
    instruction?: string,
  ) {
    return request<ResumeDetail>(`/api/resumes/${resumeId}/ai-rewrite`, {
      method: "POST",
      body: JSON.stringify({
        provider_id: providerId ?? null,
        target_role: targetRole?.trim() || null,
        instruction: instruction?.trim() || null,
      }),
    });
  },
  syncResumeToBoss(
    resumeId: number,
    input: { agent_id?: string | null; dry_run: boolean },
  ) {
    return request<TaskItem>(`/api/resumes/${resumeId}/sync-boss`, {
      method: "POST",
      body: JSON.stringify({
        agent_id: input.agent_id || null,
        dry_run: input.dry_run,
      }),
    });
  },
  getJobPreference() {
    return request<JobPreference>("/api/jobs/preferences");
  },
  updateJobPreference(input: JobPreferenceUpdateInput) {
    return request<JobPreference>("/api/jobs/preferences", {
      method: "PUT",
      body: JSON.stringify(input),
    });
  },
  listJobs(status?: string) {
    const query =
      status && status !== "all"
        ? `?status=${encodeURIComponent(status)}&limit=100`
        : "?limit=100";
    return request<BossJobListData>(`/api/jobs${query}`);
  },
  importJobs(
    items: Array<{
      boss_job_id: string;
      title: string;
      company: string;
      city?: string;
      salary?: string;
      job_url?: string;
      jd_text?: string;
    }>,
  ) {
    return request<{ created: number; updated: number; skipped: number; items: BossJobItem[] }>(
      "/api/jobs/import",
      {
        method: "POST",
        body: JSON.stringify({ items }),
      },
    );
  },
  scanBossJobs(input: {
    agent_id?: string | null;
    keywords: string[];
    city?: string | null;
    max_jobs: number;
    dry_run: boolean;
  }) {
    return request<TaskItem>("/api/jobs/scan", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  aiScoreJob(jobId: number, providerId?: number | null) {
    return request<BossJobItem>(`/api/jobs/${jobId}/ai-score`, {
      method: "POST",
      body: JSON.stringify({ provider_id: providerId ?? null }),
    });
  },
  batchScoreJobs(input: { limit?: number; provider_id?: number | null }) {
    return request<{
      scored: number;
      failed: number;
      items: BossJobItem[];
      errors: Array<{ job_id: number; title: string; error: string }>;
    }>("/api/jobs/ai-score-batch", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  applyBossJob(
    jobId: number,
    input: { agent_id?: string | null; greeting?: string | null; dry_run: boolean },
  ) {
    return request<{ job: BossJobItem; task: TaskItem }>(`/api/jobs/${jobId}/apply`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
  skipBossJob(jobId: number) {
    return request<BossJobItem>(`/api/jobs/${jobId}/skip`, {
      method: "POST",
    });
  },
  restoreBossJob(jobId: number) {
    return request<BossJobItem>(`/api/jobs/${jobId}/restore`, {
      method: "POST",
    });
  },
  autoApplyJobs(input: { agent_id?: string | null; dry_run: boolean; max_count?: number }) {
    return request<{
      dispatched_count: number;
      dry_run: boolean;
      min_score: number;
      items: Array<{ job_id: number; title: string; company: string; match_score: number }>;
    }>("/api/jobs/auto-apply", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
};
