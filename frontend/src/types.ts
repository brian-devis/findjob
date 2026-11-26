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

export type TaskType =
  | "PING"
  | "SYSTEM_INFO"
  | "BOSS_CHECK_LOGIN"
  | "BOSS_SYNC_RESUME"
  | "BOSS_SCAN_JOBS"
  | "BOSS_APPLY_JOB";

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
  api_key?: string | null;
  enabled?: boolean;
}

export interface AuditLogItem {
  id: number;
  ts: string;
  actor: string;
  action: string;
  target: string;
  detail: Record<string, unknown>;
}

export interface ResumeAIReview {
  score: number;
  summary: string;
  strengths: string[];
  issues: string[];
  suggestions: string[];
  target_role?: string;
  provider_name?: string;
  model?: string;
  reviewed_at?: string;
}

export interface ResumeSummary {
  id: number;
  title: string;
  target_role: string | null;
  source_filename: string | null;
  source_format: string;
  parent_id: number | null;
  is_active: boolean;
  ai_review_json: ResumeAIReview | null;
  synced_to_boss_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResumeDetail extends ResumeSummary {
  raw_content: string;
  structured_json: Record<string, unknown>;
}

export interface CreateResumeInput {
  title: string;
  target_role?: string | null;
  source_format?: string;
  raw_content: string;
}

export interface UpdateResumeInput {
  title?: string;
  target_role?: string | null;
  raw_content?: string;
}

export type BossJobStatus =
  | "discovered"
  | "scored"
  | "approved"
  | "applying"
  | "applied"
  | "skipped"
  | "failed";

export interface JobPreference {
  id: number;
  keywords: string[];
  cities: string[];
  salary_min: number | null;
  salary_max: number | null;
  exclude_companies: string[];
  exclude_keywords: string[];
  auto_apply_enabled: boolean;
  auto_apply_min_score: number;
  daily_apply_limit: number;
  apply_interval_seconds: number;
  greeting_template: string | null;
  provider_id: number | null;
  updated_at: string;
}

export interface JobPreferenceUpdateInput {
  keywords: string[];
  cities: string[];
  salary_min: number | null;
  salary_max: number | null;
  exclude_companies: string[];
  exclude_keywords: string[];
  auto_apply_enabled: boolean;
  auto_apply_min_score: number;
  daily_apply_limit: number;
  apply_interval_seconds: number;
  greeting_template: string | null;
  provider_id: number | null;
}

export interface BossJobItem {
  id: number;
  boss_job_id: string;
  title: string;
  company: string;
  city: string | null;
  salary: string | null;
  experience: string | null;
  education: string | null;
  recruiter: string | null;
  job_url: string | null;
  jd_text: string;
  tags: string[];
  match_score: number | null;
  match_reason: string | null;
  ai_greeting: string | null;
  status: BossJobStatus | string;
  resume_id: number | null;
  apply_task_id: string | null;
  last_error: string | null;
  applied_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface BossJobListData {
  items: BossJobItem[];
  total: number;
  applied_today: number;
  daily_apply_limit: number;
  auto_apply_enabled: boolean;
  auto_apply_min_score: number;
  stats?: {
    discovered: number;
    scored: number;
    applying: number;
    applied: number;
    failed: number;
    skipped: number;
    high_score_ready: number;
  };
}
