import { FormEvent, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type {
  AgentItem,
  BossJobItem,
  BossJobListData,
  JobPreference,
  ProviderItem,
} from "../types";

interface Props {
  preference: JobPreference | null;
  jobsData: BossJobListData;
  agents: AgentItem[];
  providers: ProviderItem[];
  statusFilter: string;
  onStatusFilterChange: (status: string) => void;
  onRefresh: () => Promise<void>;
}

const JOB_STATUS_OPTIONS = [
  "all",
  "discovered",
  "scored",
  "applying",
  "applied",
  "failed",
  "skipped",
];

function splitCommaList(raw: string): string[] {
  return raw
    .split(/[，,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function statusPillClass(status: string): string {
  switch (status) {
    case "applied":
      return "pill-green";
    case "scored":
    case "applying":
      return "pill-blue";
    case "failed":
      return "pill-red";
    case "skipped":
      return "pill-gray";
    default:
      return "pill-amber";
  }
}

export function JobsPanel({
  preference,
  jobsData,
  agents,
  providers,
  statusFilter,
  onStatusFilterChange,
  onRefresh,
}: Props) {
  const [keywordsText, setKeywordsText] = useState("");
  const [citiesText, setCitiesText] = useState("");
  const [salaryMin, setSalaryMin] = useState("");
  const [salaryMax, setSalaryMax] = useState("");
  const [excludeCompaniesText, setExcludeCompaniesText] = useState("");
  const [excludeKeywordsText, setExcludeKeywordsText] = useState("");
  const [autoApplyEnabled, setAutoApplyEnabled] = useState(false);
  const [autoApplyMinScore, setAutoApplyMinScore] = useState(80);
  const [dailyApplyLimit, setDailyApplyLimit] = useState(30);
  const [applyIntervalSeconds, setApplyIntervalSeconds] = useState(45);
  const [greetingTemplate, setGreetingTemplate] = useState("");
  const [prefProviderId, setPrefProviderId] = useState<string>("");

  const [scanAgentId, setScanAgentId] = useState<string>("");
  const [scanKeywords, setScanKeywords] = useState("");
  const [scanCity, setScanCity] = useState("");
  const [scanMaxJobs, setScanMaxJobs] = useState(15);
  const [scanDryRun, setScanDryRun] = useState(false);

  const [impBossId, setImpBossId] = useState("");
  const [impTitle, setImpTitle] = useState("");
  const [impCompany, setImpCompany] = useState("");
  const [impCity, setImpCity] = useState("");
  const [impSalary, setImpSalary] = useState("");
  const [impJd, setImpJd] = useState("");

  const [selectedJob, setSelectedJob] = useState<BossJobItem | null>(null);
  const [applyGreeting, setApplyGreeting] = useState("");
  const [applyDryRun, setApplyDryRun] = useState(true);
  const [autoBatchDryRun, setAutoBatchDryRun] = useState(true);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const activeAgents = agents.filter((a) => a.status === "active");
  const enabledProviders = providers.filter((p) => p.enabled);

  useEffect(() => {
    if (!preference) return;
    setKeywordsText(preference.keywords.join(", "));
    setCitiesText(preference.cities.join(", "));
    setSalaryMin(preference.salary_min !== null ? String(preference.salary_min) : "");
    setSalaryMax(preference.salary_max !== null ? String(preference.salary_max) : "");
    setExcludeCompaniesText(preference.exclude_companies.join(", "));
    setExcludeKeywordsText(preference.exclude_keywords.join(", "));
    setAutoApplyEnabled(preference.auto_apply_enabled);
    setAutoApplyMinScore(preference.auto_apply_min_score);
    setDailyApplyLimit(preference.daily_apply_limit);
    setApplyIntervalSeconds(preference.apply_interval_seconds);
    setGreetingTemplate(preference.greeting_template ?? "");
    setPrefProviderId(preference.provider_id !== null ? String(preference.provider_id) : "");
  }, [preference]);

  useEffect(() => {
    if (!selectedJob) return;
    const latest = jobsData.items.find((j) => j.id === selectedJob.id);
    if (latest) {
      setSelectedJob(latest);
      if (latest.ai_greeting && !applyGreeting) {
        setApplyGreeting(latest.ai_greeting);
      }
    }
  }, [jobsData.items, selectedJob, applyGreeting]);

  async function safeRefresh(successMsg?: string) {
    if (successMsg) setNotice(successMsg);
    try {
      await onRefresh();
    } catch {
      setError("操作已成功，但刷新列表失败，请点击刷新重试");
    }
  }

  async function persistPreference(nextAutoEnabled: boolean, customNotice?: string) {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      await api.updateJobPreference({
        keywords: splitCommaList(keywordsText),
        cities: splitCommaList(citiesText),
        salary_min: salaryMin.trim() ? Number(salaryMin) : null,
        salary_max: salaryMax.trim() ? Number(salaryMax) : null,
        exclude_companies: splitCommaList(excludeCompaniesText),
        exclude_keywords: splitCommaList(excludeKeywordsText),
        auto_apply_enabled: nextAutoEnabled,
        auto_apply_min_score: Number(autoApplyMinScore) || 80,
        daily_apply_limit: Number(dailyApplyLimit) || 30,
        apply_interval_seconds: Number(applyIntervalSeconds) || 45,
        greeting_template: greetingTemplate.trim() || null,
        provider_id: prefProviderId ? Number(prefProviderId) : null,
      });
      await safeRefresh(
        customNotice ??
          `求职偏好已保存（当前模式：${nextAutoEnabled ? "高分自动投递" : "手动逐条确认"}）`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "保存求职偏好失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSavePreference(e: FormEvent) {
    e.preventDefault();
    await persistPreference(autoApplyEnabled);
  }

  async function handleToggleAutoApply(nextValue: boolean) {
    setAutoApplyEnabled(nextValue);
    await persistPreference(
      nextValue,
      nextValue
        ? `已切换为「高分自动投递模式」（阈值 ≥ ${autoApplyMinScore} 分）`
        : "已切换为「手动逐条确认模式」（默认安全模式）",
    );
  }

  async function handleScanJobs(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const kws = splitCommaList(scanKeywords || keywordsText);
      const task = await api.scanBossJobs({
        agent_id: scanAgentId || null,
        keywords: kws,
        city: scanCity.trim() || null,
        max_jobs: scanMaxJobs,
        dry_run: scanDryRun,
      });
      await safeRefresh(`已下发 BOSS 岗位扫描任务（Task ${task.task_id.slice(0, 8)}）`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "下发扫描任务失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleImportJob(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const res = await api.importJobs([
        {
          boss_job_id: impBossId.trim() || `manual-${Date.now()}`,
          title: impTitle.trim(),
          company: impCompany.trim(),
          city: impCity.trim() || undefined,
          salary: impSalary.trim() || undefined,
          jd_text: impJd.trim() || undefined,
        },
      ]);
      setImpBossId("");
      setImpTitle("");
      setImpCompany("");
      setImpCity("");
      setImpSalary("");
      setImpJd("");
      if (res.items[0]) {
        setSelectedJob(res.items[0]);
      }
      await safeRefresh(
        `已导入岗位：新增 ${res.created}，更新 ${res.updated}，黑名单过滤 ${res.skipped}`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "导入岗位失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleScoreJob(job: BossJobItem) {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const updated = await api.aiScoreJob(
        job.id,
        prefProviderId ? Number(prefProviderId) : null,
      );
      setSelectedJob(updated);
      setApplyGreeting(updated.ai_greeting ?? "");
      await safeRefresh(`「${updated.title}」AI 匹配评分：${updated.match_score ?? 0} 分`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "AI 匹配评分失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleApplyJob(job: BossJobItem) {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const res = await api.applyBossJob(job.id, {
        agent_id: scanAgentId || null,
        greeting: applyGreeting.trim() || job.ai_greeting || null,
        dry_run: applyDryRun,
      });
      setSelectedJob(res.job);
      await safeRefresh(
        `已下发${applyDryRun ? "预演" : "实操"}投递任务（Task ${res.task.task_id.slice(0, 8)}）`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "下发投递任务失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleSkipJob(job: BossJobItem) {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const updated = await api.skipBossJob(job.id);
      if (selectedJob?.id === updated.id) setSelectedJob(updated);
      await safeRefresh(`已忽略岗位「${updated.title}」`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "忽略岗位失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleBatchScore() {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const res = await api.batchScoreJobs({
        limit: 10,
        provider_id: prefProviderId ? Number(prefProviderId) : null,
      });
      await safeRefresh(
        `批量 AI 评分完成：成功 ${res.scored} 条${res.failed > 0 ? `，失败 ${res.failed} 条` : ""}`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "批量 AI 评分失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRestoreJob(job: BossJobItem) {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const updated = await api.restoreBossJob(job.id);
      if (selectedJob?.id === updated.id) setSelectedJob(updated);
      await safeRefresh(`已恢复岗位「${updated.title}」至 ${updated.status}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "恢复岗位失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleAutoApplyBatch() {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const res = await api.autoApplyJobs({
        agent_id: scanAgentId || null,
        dry_run: autoBatchDryRun,
        max_count: 5,
      });
      await safeRefresh(
        `已按 ≥${res.min_score} 分自动下发 ${res.dispatched_count} 个投递任务（${res.dry_run ? "预演" : "实操"}）`,
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "批量自动投递失败");
    } finally {
      setBusy(false);
    }
  }

  const stats = jobsData.stats ?? {
    discovered: 0,
    scored: 0,
    applying: 0,
    applied: 0,
    failed: 0,
    skipped: 0,
    high_score_ready: 0,
  };

  return (
    <div className="stack">
      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-success">{notice}</div>}

      <div className="stats-grid">
        <div className="stat-card">
          <span className="muted">待 AI 评分</span>
          <strong className="stat-value">{stats.discovered}</strong>
        </div>
        <div className="stat-card">
          <span className="muted">高分待投（≥{jobsData.auto_apply_min_score}分）</span>
          <strong className="stat-value">{stats.high_score_ready}</strong>
        </div>
        <div className="stat-card">
          <span className="muted">今日配额（已投/进行中）</span>
          <strong className="stat-value">
            {jobsData.applied_today}/{jobsData.daily_apply_limit}
          </strong>
        </div>
        <div className="stat-card">
          <span className="muted">累计已投递</span>
          <strong className="stat-value">{stats.applied}</strong>
        </div>
        <div className="stat-card">
          <span className="muted">失败 / 已忽略</span>
          <strong className="stat-value">
            {stats.failed} / {stats.skipped}
          </strong>
        </div>
      </div>

      <section className="card stack">
        <div className="section-head">
          <h2>投递策略开关与求职偏好</h2>
          <div className="toolbar">
            <label className="mode-toggle">
              <input
                type="checkbox"
                checked={autoApplyEnabled}
                disabled={busy}
                onChange={(e) => void handleToggleAutoApply(e.target.checked)}
              />
              <span>
                {autoApplyEnabled
                  ? `自动投递已开启（≥ ${autoApplyMinScore} 分可批量触发）`
                  : "手动确认模式（默认：每条岗位需人工点击投递）"}
              </span>
            </label>
          </div>
        </div>

        <form className="task-form" onSubmit={handleSavePreference}>
          <div className="form-grid">
            <label className="field">
              <span>搜索关键词（逗号分隔）</span>
              <input
                type="text"
                placeholder="例如：Python, FastAPI, AI Agent"
                value={keywordsText}
                onChange={(e) => setKeywordsText(e.target.value)}
              />
            </label>
            <label className="field">
              <span>目标城市（逗号分隔）</span>
              <input
                type="text"
                placeholder="例如：上海, 北京, 杭州"
                value={citiesText}
                onChange={(e) => setCitiesText(e.target.value)}
              />
            </label>
            <label className="field">
              <span>最低月薪（K）</span>
              <input
                type="number"
                min={0}
                value={salaryMin}
                onChange={(e) => setSalaryMin(e.target.value)}
              />
            </label>
            <label className="field">
              <span>最高月薪（K）</span>
              <input
                type="number"
                min={0}
                value={salaryMax}
                onChange={(e) => setSalaryMax(e.target.value)}
              />
            </label>
            <label className="field">
              <span>自动投递最低分阈值</span>
              <input
                type="number"
                min={0}
                max={100}
                value={autoApplyMinScore}
                onChange={(e) => setAutoApplyMinScore(Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>每日投递上限</span>
              <input
                type="number"
                min={1}
                max={200}
                value={dailyApplyLimit}
                onChange={(e) => setDailyApplyLimit(Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>投递冷却间隔（秒）</span>
              <input
                type="number"
                min={5}
                max={600}
                value={applyIntervalSeconds}
                onChange={(e) => setApplyIntervalSeconds(Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>默认匹配 AI Provider</span>
              <select
                value={prefProviderId}
                onChange={(e) => setPrefProviderId(e.target.value)}
              >
                <option value="">首个已启用模型</option>
                {enabledProviders.map((p) => (
                  <option key={p.id} value={String(p.id)}>
                    {p.name} ({p.model})
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="form-grid">
            <label className="field">
              <span>屏蔽公司关键词（逗号分隔）</span>
              <input
                type="text"
                placeholder="例如：外包, 劳务派遣"
                value={excludeCompaniesText}
                onChange={(e) => setExcludeCompaniesText(e.target.value)}
              />
            </label>
            <label className="field">
              <span>屏蔽职位/JD关键词（逗号分隔）</span>
              <input
                type="text"
                placeholder="例如：驻场, 销售"
                value={excludeKeywordsText}
                onChange={(e) => setExcludeKeywordsText(e.target.value)}
              />
            </label>
          </div>

          <label className="field">
            <span>打招呼话术偏好提示（可选，AI 生成开场白时会参考）</span>
            <input
              type="text"
              placeholder="例如：简洁真诚，重点突出 FastAPI 与 Playwright 实战成果"
              value={greetingTemplate}
              onChange={(e) => setGreetingTemplate(e.target.value)}
            />
          </label>

          <div className="toolbar">
            <button className="btn btn-primary" type="submit" disabled={busy}>
              保存偏好配置
            </button>
            {autoApplyEnabled && (
              <>
                <label className="checkbox-inline">
                  <input
                    type="checkbox"
                    checked={autoBatchDryRun}
                    onChange={(e) => setAutoBatchDryRun(e.target.checked)}
                  />
                  <span>自动批量预演（dry_run）</span>
                </label>
                <button
                  className="btn btn-warning"
                  type="button"
                  disabled={busy || activeAgents.length === 0}
                  onClick={() => void handleAutoApplyBatch()}
                >
                  执行一轮高分自动投递
                </button>
              </>
            )}
          </div>
        </form>
      </section>

      <div className="two-col">
        <section className="card">
          <div className="section-head">
            <h2>触发 BOSS 岗位扫描</h2>
            <span className="muted">通过 Local Agent 在桌面浏览器抓取岗位卡片</span>
          </div>
          <form className="task-form" onSubmit={handleScanJobs}>
            <div className="form-grid">
              <label className="field">
                <span>目标 Agent</span>
                <select value={scanAgentId} onChange={(e) => setScanAgentId(e.target.value)}>
                  <option value="">自动分配（任意在线 Agent）</option>
                  {activeAgents.map((a) => (
                    <option key={a.agent_id} value={a.agent_id}>
                      {a.name} ({a.online ? "在线" : "离线"})
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>本次关键词（留空则用偏好）</span>
                <input
                  type="text"
                  placeholder="Python 后端"
                  value={scanKeywords}
                  onChange={(e) => setScanKeywords(e.target.value)}
                />
              </label>
              <label className="field">
                <span>城市（可选）</span>
                <input
                  type="text"
                  placeholder="上海"
                  value={scanCity}
                  onChange={(e) => setScanCity(e.target.value)}
                />
              </label>
              <label className="field">
                <span>抓取上限</span>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={scanMaxJobs}
                  onChange={(e) => setScanMaxJobs(Number(e.target.value))}
                />
              </label>
            </div>
            <div className="toolbar">
              <label className="checkbox-inline">
                <input
                  type="checkbox"
                  checked={scanDryRun}
                  onChange={(e) => setScanDryRun(e.target.checked)}
                />
                <span>仅预演校验搜索页（dry_run）</span>
              </label>
              <button
                className="btn btn-primary"
                type="submit"
                disabled={busy || activeAgents.length === 0}
              >
                下发扫描任务
              </button>
            </div>
          </form>
        </section>

        <section className="card">
          <div className="section-head">
            <h2>快速录入测试岗位</h2>
            <span className="muted">无需等待浏览器即可联调 AI 评分与话术</span>
          </div>
          <form className="task-form" onSubmit={handleImportJob}>
            <div className="form-grid">
              <label className="field">
                <span>职位名称</span>
                <input
                  type="text"
                  placeholder="Python 高级后端"
                  value={impTitle}
                  onChange={(e) => setImpTitle(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                <span>公司名称</span>
                <input
                  type="text"
                  placeholder="某某科技有限公司"
                  value={impCompany}
                  onChange={(e) => setImpCompany(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                <span>城市</span>
                <input
                  type="text"
                  placeholder="上海"
                  value={impCity}
                  onChange={(e) => setImpCity(e.target.value)}
                />
              </label>
              <label className="field">
                <span>薪资</span>
                <input
                  type="text"
                  placeholder="30-45K"
                  value={impSalary}
                  onChange={(e) => setImpSalary(e.target.value)}
                />
              </label>
              <label className="field">
                <span>BOSS ID（可选）</span>
                <input
                  type="text"
                  placeholder="自动生成"
                  value={impBossId}
                  onChange={(e) => setImpBossId(e.target.value)}
                />
              </label>
            </div>
            <label className="field">
              <span>JD 要求</span>
              <textarea
                rows={2}
                placeholder="粘贴岗位职责与任职要求..."
                value={impJd}
                onChange={(e) => setImpJd(e.target.value)}
              />
            </label>
            <div>
              <button className="btn btn-secondary" type="submit" disabled={busy}>
                导入岗位队列
              </button>
            </div>
          </form>
        </section>
      </div>

      <section className="card">
        <div className="section-head">
          <h2>
            岗位与投递漏斗（{jobsData.total}）· 今日已投递/进行中{" "}
            {jobsData.applied_today}/{jobsData.daily_apply_limit}
          </h2>
          <div className="toolbar">
            <button
              className="btn btn-secondary"
              type="button"
              disabled={busy || enabledProviders.length === 0 || stats.discovered === 0}
              onClick={() => void handleBatchScore()}
            >
              批量 AI 评分（最多 10 条）
            </button>
            <select
              value={statusFilter}
              onChange={(e) => onStatusFilterChange(e.target.value)}
            >
              {JOB_STATUS_OPTIONS.map((s) => (
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

        {jobsData.items.length === 0 ? (
          <p className="empty">暂无岗位记录，请先通过 Agent 扫描或手动录入测试岗位</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>职位</th>
                  <th>公司</th>
                  <th>城市 / 薪资</th>
                  <th>AI 匹配度</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {jobsData.items.map((j) => (
                  <tr
                    key={j.id}
                    className={selectedJob?.id === j.id ? "row-selected" : undefined}
                  >
                    <td>
                      <button
                        className="link-btn"
                        type="button"
                        onClick={() => {
                          setSelectedJob(j);
                          setApplyGreeting(j.ai_greeting ?? "");
                        }}
                      >
                        <strong>{j.title}</strong>
                      </button>
                    </td>
                    <td>{j.company}</td>
                    <td className="muted">
                      {[j.city, j.salary].filter(Boolean).join(" · ") || "—"}
                    </td>
                    <td>
                      {j.match_score !== null ? (
                        <span className="pill pill-blue">{j.match_score} 分</span>
                      ) : (
                        "未评分"
                      )}
                    </td>
                    <td>
                      <span className={`pill ${statusPillClass(j.status)}`}>{j.status}</span>
                    </td>
                    <td className="actions">
                      <button
                        className="btn btn-sm btn-secondary"
                        type="button"
                        disabled={busy || enabledProviders.length === 0}
                        onClick={() => void handleScoreJob(j)}
                      >
                        AI 评分
                      </button>
                      <button
                        className="btn btn-sm btn-primary"
                        type="button"
                        onClick={() => {
                          setSelectedJob(j);
                          setApplyGreeting(j.ai_greeting ?? "");
                        }}
                      >
                        详情/投递
                      </button>
                      {j.status !== "applied" && j.status !== "skipped" && (
                        <button
                          className="btn btn-sm btn-ghost"
                          type="button"
                          disabled={busy}
                          onClick={() => void handleSkipJob(j)}
                        >
                          忽略
                        </button>
                      )}
                      {(j.status === "skipped" || j.status === "failed") && (
                        <button
                          className="btn btn-sm btn-warning"
                          type="button"
                          disabled={busy}
                          onClick={() => void handleRestoreJob(j)}
                        >
                          恢复
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selectedJob && (
        <section className="card stack">
          <div className="section-head">
            <h3>
              岗位详情与确认投递：{selectedJob.title} @ {selectedJob.company}
            </h3>
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() => setSelectedJob(null)}
            >
              关闭
            </button>
          </div>
          <div className="detail-grid">
            <div>
              <span className="muted">状态：</span>
              {selectedJob.status}
            </div>
            <div>
              <span className="muted">AI 匹配度：</span>
              {selectedJob.match_score !== null ? `${selectedJob.match_score} 分` : "未评分"}
            </div>
            <div>
              <span className="muted">BOSS ID：</span>
              <span className="mono">{selectedJob.boss_job_id}</span>
            </div>
            <div>
              <span className="muted">最近备注/错误：</span>
              {selectedJob.last_error || "无"}
            </div>
          </div>
          {selectedJob.match_reason && (
            <div className="review-box">
              <strong>AI 匹配分析：</strong>
              <p>{selectedJob.match_reason}</p>
            </div>
          )}
          <label className="field">
            <span>开场白 / 打招呼文案（发送前可自由微调）</span>
            <textarea
              rows={3}
              value={applyGreeting}
              onChange={(e) => setApplyGreeting(e.target.value)}
              placeholder="点击「AI 评分」自动生成个性化打招呼文案，或在此直接输入..."
            />
          </label>
          <div className="toolbar">
            <label className="checkbox-inline">
              <input
                type="checkbox"
                checked={applyDryRun}
                onChange={(e) => setApplyDryRun(e.target.checked)}
              />
              <span>预演模式（dry_run，仅检查详情页，不点击实际沟通）</span>
            </label>
            <button
              className="btn btn-secondary"
              type="button"
              disabled={busy || enabledProviders.length === 0}
              onClick={() => void handleScoreJob(selectedJob)}
            >
              重新 AI 评分与生成话术
            </button>
            <button
              className="btn btn-primary"
              type="button"
              disabled={
                busy ||
                activeAgents.length === 0 ||
                selectedJob.status === "applied" ||
                selectedJob.status === "applying"
              }
              onClick={() => void handleApplyJob(selectedJob)}
            >
              {applyDryRun ? "预演投递检查" : "确认发送打招呼（投递）"}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
