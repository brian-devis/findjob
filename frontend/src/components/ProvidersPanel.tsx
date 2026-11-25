import { FormEvent, useState } from "react";
import { api, ApiError } from "../api";
import type { ApiFormat, ProviderItem } from "../types";

interface Props {
  providers: ProviderItem[];
  onRefresh: () => Promise<void>;
}

export function ProvidersPanel({ providers, onRefresh }: Props) {
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://api.asgo.click:8443/v1");
  const [apiFormat, setApiFormat] = useState<ApiFormat>("openai");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.createProvider({
        name: name.trim(),
        base_url: baseUrl.trim(),
        api_format: apiFormat,
        model: model.trim(),
        api_key: apiKey.trim() || null,
        enabled: true,
      });
      setName("");
      setModel("");
      setApiKey("");
      await onRefresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建 AI Provider 失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggle(provider: ProviderItem) {
    setError(null);
    setBusy(true);
    try {
      await api.updateProvider(provider.id, { enabled: !provider.enabled });
      await onRefresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "更新状态失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(provider: ProviderItem) {
    if (!window.confirm(`确认删除 AI Provider「${provider.name}」？`)) {
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await api.deleteProvider(provider.id);
      await onRefresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <section className="card">
        <div className="section-head">
          <h2>新增 AI Provider</h2>
          <span className="muted">API Key 使用 AES-256-GCM 加密存储，列表仅展示掩码</span>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        <form className="task-form" onSubmit={handleCreate}>
          <div className="form-grid">
            <label className="field">
              <span>名称</span>
              <input
                type="text"
                placeholder="例如 deepseek-prod"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={64}
                required
              />
            </label>

            <label className="field">
              <span>协议格式</span>
              <select
                value={apiFormat}
                onChange={(e) => setApiFormat(e.target.value as ApiFormat)}
              >
                <option value="openai">openai</option>
                <option value="anthropic">anthropic</option>
              </select>
            </label>

            <label className="field">
              <span>模型标识</span>
              <input
                type="text"
                placeholder="例如 deepseek-v4-pro"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                maxLength={64}
                required
              />
            </label>
          </div>

          <div className="form-grid">
            <label className="field">
              <span>Base URL</span>
              <input
                type="url"
                placeholder="https://api.example.com/v1"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                maxLength={255}
                required
              />
            </label>

            <label className="field">
              <span>API Key（可选）</span>
              <input
                type="password"
                autoComplete="off"
                placeholder="sk-..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </label>
          </div>

          <div>
            <button className="btn btn-primary" type="submit" disabled={busy}>
              保存 Provider
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="section-head">
          <h2>AI Provider 列表（{providers.length}）</h2>
          <button className="btn btn-ghost" type="button" onClick={() => void onRefresh()}>
            刷新
          </button>
        </div>

        {providers.length === 0 ? (
          <p className="empty">暂无已配置的 AI Provider</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>状态</th>
                  <th>格式</th>
                  <th>模型</th>
                  <th>Base URL</th>
                  <th>API Key</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {providers.map((p) => (
                  <tr key={p.id}>
                    <td><strong>{p.name}</strong></td>
                    <td>
                      <span className={`pill ${p.enabled ? "pill-green" : "pill-gray"}`}>
                        {p.enabled ? "已启用" : "已禁用"}
                      </span>
                    </td>
                    <td>{p.api_format}</td>
                    <td className="mono">{p.model}</td>
                    <td className="mono">{p.base_url}</td>
                    <td className="mono">{p.api_key_masked || "未配置"}</td>
                    <td className="actions">
                      <button
                        className="btn btn-sm btn-secondary"
                        type="button"
                        disabled={busy}
                        onClick={() => void handleToggle(p)}
                      >
                        {p.enabled ? "禁用" : "启用"}
                      </button>
                      <button
                        className="btn btn-sm btn-danger"
                        type="button"
                        disabled={busy}
                        onClick={() => void handleDelete(p)}
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
    </div>
  );
}
