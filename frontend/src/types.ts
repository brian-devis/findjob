export interface ApiEnvelope<T> {
  code: number;
  message: string;
  data: T;
}

export interface AdminUser {
  id?: number;
  username: string;
}

export interface AgentItem {
  agent_id: string;
  name: string;
  status: "active" | "revoked" | string;
  secret_version: number;
  last_seen_at: string | null;
  created_at: string;
  online: boolean;
}

export interface AgentSecret {
  agent_id: string;
  secret: string;
}

export type TaskStatus =
  | "queued"
  | "dispatched"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type TaskType = "PING" | "SYSTEM_INFO";

export interface TaskItem {
  task_id: string;
  agent_id: string | null;
  type: TaskType | string;
  status: TaskStatus;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: string | null;
  priority: number;
  attempt: number;
  max_attempts: number;
  timeout_seconds: number;
  idempotency_key: string | null;
  created_at: string;
  dispatched_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface PagedResult<T> {
  items: T[];
  total: number;
}

export interface CreateTaskInput {
  type: TaskType;
  agent_id?: string | null;
  payload: Record<string, unknown>;
  priority: number;
  max_attempts: number;
  timeout_seconds: number;
}

export type ApiFormat = "openai" | "anthropic";

export interface ProviderItem {
  id: number;
  name: string;
  base_url: string;
  api_format: ApiFormat | string;
  model: string;
  api_key_masked: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateProviderInput {
  name: string;
  base_url: string;
  api_format: ApiFormat;
  model: string;
  api_key?: string | null;
  enabled: boolean;
}

export interface UpdateProviderInput {
  name?: string;
  base_url?: string;
  api_format?: ApiFormat;
  model?: string;
  api_key?: string;
  enabled?: boolean;
}
