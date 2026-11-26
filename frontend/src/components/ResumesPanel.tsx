import { FormEvent, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type {
  AgentItem,
  ProviderItem,
  ResumeDetail,
  ResumeSummary,
  TaskItem,
} from "../types";

interface Props {
  resumes: ResumeSummary[];
  providers: ProviderItem[];
  agents: AgentItem[];
  tasks: TaskItem[];
  onRefresh: () => Promise<void>;
}

export function ResumesPanel({ resumes, providers, agents, tasks, onRefresh }: Props) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ResumeDetail | null>(null);

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadRole, setUploadRole] = useState("");

  const [newTitle, setNewTitle] = useState("");
  const [newRole, setNewRole] = useState("");
  const [newContent, setNewContent] = useState("");

  const [editTitle, setEditTitle] = useState("");
  const [editRole, setEditRole] = useState("");
  const [editContent, setEditContent] = useState("");

  const [providerId, setProviderId] = useState<string>("");
  const [instruction, setInstruction] = useState("");
  const [syncAgentId, setSyncAgentId] = useState<string>("");
  const [syncDryRun, setSyncDryRun] = useState<boolean>(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const enabledProviders = providers.filter((p) => p.enabled);
  const activeAgents = agents.filter((a) => a.status === "active");
  const latestSyncTask = detail
    ? tasks.find(
        (t) =>
          t.type === "BOSS_SYNC_RESUME" &&
          (t.payload as Record<string, unknown> | undefined)?.resume_id === detail.id,
      ) ?? null
    : null;
  const syncResult = latestSyncTask?.result as Record<string, unknown> | null | undefined;

  useEffect(() => {
    if (resumes.length === 0) {
      setSelectedId(null);
      setDetail(null);
      return;
    }
    if (selectedId === null || !resumes.some((r) => r.id === selectedId)) {
      const preferred = resumes.find((r) => r.is_active) ?? resumes[0];
      setSelectedId(preferred.id);
    }
  }, [resumes, selectedId]);

  useEffect(() => {
    if (selectedId === null) return;
    let cancelled = false;
    void (async () => {
      try {
        const res = await api.getResume(selectedId);
        if (cancelled) return;
        setDetail(res);
        setEditTitle(res.title);
        setEditRole(res.target_role ?? "");
        setEditContent(res.raw_content);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "加载简历详情失败");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  async function safeRefresh(successMsg?: string) {
    if (successMsg) setNotice(successMsg);
    try {
      await onRefresh();
    } catch {
      setError("操作已成功，但刷新列表失败，请点击刷新重试");
    }
  }

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    if (!uploadFile) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const created = await api.uploadResume(uploadFile, uploadTitle, uploadRole);
      setUploadFile(null);
      setUploadTitle("");
      setUploadRole("");
      setSelectedId(created.id);
      setDetail(created);
      await safeRefresh(`已导入简历「${created.title}」（${created.source_format.toUpperCase()}）`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "上传解析简历失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateText(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const created = await api.createResume({
        title: newTitle.trim(),
        target_role: newRole.trim() || null,
        raw_content: newContent,
      });
      setNewTitle("");
      setNewRole("");
      setNewContent("");
      setSelectedId(created.id);
      setDetail(created);
      await safeRefresh(`已创建简历「${created.title}」`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建简历失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveEdit(e: FormEvent) {
    e.preventDefault();
    if (!detail) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const updated = await api.updateResume(detail.id, {
        title: editTitle.trim(),
        target_role: editRole.trim() || null,
        raw_content: editContent,
      });
      setDetail(updated);
      await safeRefresh("简历修改已保存");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存简历失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleActivate(id: number) {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const updated = await api.activateResume(id);
      if (detail?.id === id) setDetail(updated);
      await safeRefresh(`已将「${updated.title}」设为当前投递简历`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "切换激活简历失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(item: ResumeSummary) {
    if (!window.confirm(`确认删除简历「${item.title}」？`)) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      await api.deleteResume(item.id);
      if (selectedId === item.id) {
        setSelectedId(null);
        setDetail(null);
      }
      await safeRefresh("简历已删除");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除简历失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleAIReview() {
    if (!detail) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const updated = await api.aiReviewResume(
        detail.id,
        providerId ? Number(providerId) : undefined,
        editRole,
      );
      setDetail(updated);
      await safeRefresh("AI 简历审阅已完成");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "AI 审阅失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleAIRewrite() {
    if (!detail) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const created = await api.aiRewriteResume(
        detail.id,
        providerId ? Number(providerId) : undefined,
        editRole,
        instruction,
      );
      setInstruction("");
      setSelectedId(created.id);
      setDetail(created);
      setEditTitle(created.title);
      setEditRole(created.target_role ?? "");
      setEditContent(created.raw_content);
      await safeRefresh(`已生成 AI 优化版本「${created.title}」，请审阅确认后设为当前版本`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "AI 改写失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSyncBoss() {
    if (!detail) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const task = await api.syncResumeToBoss(detail.id, {
        agent_id: syncAgentId || null,
        dry_run: syncDryRun,
      });
      await safeRefresh(
        `已下发 BOSS 同步任务（${syncDryRun ? "预演模式" : "实操同步"}，Task ${task.task_id.slice(0, 8)}）`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "下发 BOSS 同步任务失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-success">{notice}</div>}

      <div className="two-col">
        <section className="card">
          <div className="section-head">
            <h2>上传 Word / PDF 简历</h2>
            <span className="muted">支持 .pdf / .docx / .md / .txt（≤ 5MB）</span>
          </div>
          <form className="task-form" onSubmit={handleUpload}>
            <label className="field">
              <span>选择文件</span>
              <input
                type="file"
                accept=".pdf,.docx,.md,.markdown,.txt"
                onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                required
              />
            </label>
            <div className="form-grid">
              <label className="field">
                <span>版本标题（可选，默认取文件名）</span>
                <input
                  type="text"
                  placeholder="例如：个人简历-原始版"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  maxLength={128}
                />
              </label>
              <label className="field">
                <span>目标岗位（可选）</span>
                <input
                  type="text"
                  placeholder="例如：Python 后端工程师"
                  value={uploadRole}
                  onChange={(e) => setUploadRole(e.target.value)}
                  maxLength={128}
                />
              </label>
            </div>
            <div>
              <button className="btn btn-primary" type="submit" disabled={busy || !uploadFile}>
                解析并导入简历
              </button>
            </div>
          </form>
        </section>

        <section className="card">
          <div className="section-head">
            <h2>新建文本 / Markdown 简历</h2>
            <span className="muted">也可直接粘贴内容创建版本</span>
          </div>
          <form className="task-form" onSubmit={handleCreateText}>
            <div className="form-grid">
              <label className="field">
                <span>版本标题</span>
                <input
                  type="text"
                  placeholder="例如：后端开发简历 v1"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  maxLength={128}
                  required
                />
              </label>
              <label className="field">
                <span>目标岗位</span>
                <input
                  type="text"
                  placeholder="例如：AI 应用工程师"
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  maxLength={128}
                />
              </label>
            </div>
            <label className="field">
              <span>简历正文</span>
              <textarea
                rows={3}
                placeholder="粘贴简历文本或 Markdown 内容..."
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                required
              />
            </label>
            <div>
              <button className="btn btn-secondary" type="submit" disabled={busy}>
                创建版本
              </button>
            </div>
          </form>
        </section>
      </div>

      <section className="card">
        <div className="section-head">
          <h2>简历版本列表（{resumes.length}）</h2>
          <button
            className="btn btn-ghost"
            type="button"
            onClick={() => void safeRefresh()}
          >
            刷新
          </button>
        </div>

        {resumes.length === 0 ? (
          <p className="empty">请先上传 Word / PDF 或粘贴创建你的第一份简历</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>标题</th>
                  <th>状态</th>
                  <th>格式</th>
                  <th>目标岗位</th>
                  <th>AI 评分</th>
                  <th>BOSS 同步</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {resumes.map((r) => (
                  <tr
                    key={r.id}
                    className={selectedId === r.id ? "row-selected" : undefined}
                  >
                    <td>
                      <button
                        className="link-btn"
                        type="button"
                        onClick={() => setSelectedId(r.id)}
                      >
                        <strong>{r.title}</strong>
                      </button>
                    </td>
                    <td>
                      <span className={`pill ${r.is_active ? "pill-green" : "pill-gray"}`}>
                        {r.is_active ? "当前激活" : "备选版本"}
                      </span>
                    </td>
                    <td className="mono">{r.source_format}</td>
                    <td>{r.target_role || "—"}</td>
                    <td>
                      {r.ai_review_json ? (
                        <span className="pill pill-blue">{r.ai_review_json.score} 分</span>
                      ) : (
                        "未审阅"
                      )}
                    </td>
                    <td className="muted">
                      {r.synced_to_boss_at
                        ? new Date(r.synced_to_boss_at).toLocaleString()
                        : "未同步"}
                    </td>
                    <td className="actions">
                      <button
                        className="btn btn-sm btn-secondary"
                        type="button"
                        onClick={() => setSelectedId(r.id)}
                      >
                        查看/AI优化
                      </button>
                      {!r.is_active && (
                        <button
                          className="btn btn-sm btn-primary"
                          type="button"
                          disabled={busy}
                          onClick={() => void handleActivate(r.id)}
                        >
                          设为当前
                        </button>
                      )}
                      <button
                        className="btn btn-sm btn-danger"
                        type="button"
                        disabled={busy}
                        onClick={() => void handleDelete(r)}
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

      {detail && (
        <section className="card stack">
          <div className="section-head">
            <h2>AI 审阅、改写与编辑：{detail.title}</h2>
            <div className="toolbar">
              <select
                value={providerId}
                onChange={(e) => setProviderId(e.target.value)}
              >
                <option value="">默认使用首个已启用 AI Provider</option>
                {enabledProviders.map((p) => (
                  <option key={p.id} value={String(p.id)}>
                    {p.name} ({p.model})
                  </option>
                ))}
              </select>
              <button
                className="btn btn-primary"
                type="button"
                disabled={busy || enabledProviders.length === 0}
                onClick={() => void handleAIReview()}
              >
                {busy ? "处理中..." : "AI 审阅诊断"}
              </button>
            </div>
          </div>

          {enabledProviders.length === 0 && (
            <div className="alert alert-error">
              当前尚未配置启用的 AI Provider，请先到「AI Providers」页添加模型后即可使用 AI 审阅与改写。
            </div>
          )}

          {detail.ai_review_json && (
            <div className="review-box">
              <div className="section-head">
                <h3>
                  AI 审阅评分：{detail.ai_review_json.score} / 100
                  {detail.ai_review_json.model && (
                    <span className="muted">（模型：{detail.ai_review_json.model}）</span>
                  )}
                </h3>
              </div>
              <p>{detail.ai_review_json.summary}</p>
              <div className="three-col">
                <div>
                  <strong>核心优势</strong>
                  <ul>
                    {detail.ai_review_json.strengths.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <strong>待改进问题</strong>
                  <ul>
                    {detail.ai_review_json.issues.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <strong>落地修改建议</strong>
                  <ul>
                    {detail.ai_review_json.suggestions.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          <div className="inline-form">
            <input
              type="text"
              placeholder="补充 AI 改写要求（可选，例如：突出高并发 FastAPI 经验、精简篇幅至一页）"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
            />
            <button
              className="btn btn-secondary"
              type="button"
              disabled={busy || enabledProviders.length === 0}
              onClick={() => void handleAIRewrite()}
            >
              {busy ? "生成中..." : "AI 改写生成新版本"}
            </button>
          </div>

          <form className="task-form" onSubmit={handleSaveEdit}>
            <div className="form-grid">
              <label className="field">
                <span>标题</span>
                <input
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  maxLength={128}
                  required
                />
              </label>
              <label className="field">
                <span>目标岗位</span>
                <input
                  type="text"
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value)}
                  maxLength={128}
                />
              </label>
            </div>
            <label className="field">
              <span>简历正文（可直接人工微调保存，后续将同步给 BOSS 直聘）</span>
              <textarea
                rows={12}
                className="mono"
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                required
              />
            </label>
            <div className="toolbar">
              <button className="btn btn-primary" type="submit" disabled={busy}>
                保存修改
              </button>
              <a
                className="btn btn-secondary"
                href={`/api/resumes/${detail.id}/export?format=docx`}
                download
              >
                导出 Word (.docx)
              </a>
              <a
                className="btn btn-ghost"
                href={`/api/resumes/${detail.id}/export?format=md`}
                download
              >
                导出 Markdown (.md)
              </a>
            </div>
          </form>

          <div className="review-box stack">
            <div className="section-head">
              <h3>同步到 BOSS 直聘（通过 Local Agent 本地浏览器）</h3>
              <span className="muted">
                {detail.synced_to_boss_at
                  ? `最近已同步：${new Date(detail.synced_to_boss_at).toLocaleString()}`
                  : "尚未实操同步"}
              </span>
            </div>
            <div className="toolbar">
              <select
                value={syncAgentId}
                onChange={(e) => setSyncAgentId(e.target.value)}
              >
                <option value="">自动分配（任意在线 Agent）</option>
                {activeAgents.map((a) => (
                  <option key={a.agent_id} value={a.agent_id}>
                    {a.name} ({a.online ? "在线" : "离线"})
                  </option>
                ))}
              </select>
              <label className="checkbox-inline">
                <input
                  type="checkbox"
                  checked={syncDryRun}
                  onChange={(e) => setSyncDryRun(e.target.checked)}
                />
                <span>预演模式（dry_run，仅校验登录态并预览，不改线上）</span>
              </label>
              <button
                className="btn btn-primary"
                type="button"
                disabled={busy || activeAgents.length === 0}
                onClick={() => void handleSyncBoss()}
              >
                {syncDryRun ? "预演同步检查" : "同步到 BOSS 直聘"}
              </button>
            </div>
            {latestSyncTask && (
              <div
                className={`alert ${
                  syncResult?.needs_human_action
                    ? "alert-warning"
                    : latestSyncTask.status === "succeeded"
                      ? "alert-success"
                      : latestSyncTask.status === "failed"
                        ? "alert-error"
                        : "alert-warning"
                }`}
              >
                <strong>最近同步任务（{latestSyncTask.status}）：</strong>
                {typeof syncResult?.message === "string"
                  ? syncResult.message
                  : latestSyncTask.error || "任务处理中，请留意本地浏览器状态"}
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
