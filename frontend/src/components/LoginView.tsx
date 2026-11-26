import { FormEvent, useState } from "react";
import { api, ApiError } from "../api";

interface Props {
  onSuccess: (username: string) => void;
}

export function LoginView({ onSuccess }: Props) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await api.login(username.trim(), password);
      onSuccess(data.username);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败，请检查网络或凭据");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-shell">
      <form className="card login-card" onSubmit={handleSubmit}>
        <div className="login-header">
          <div className="brand-badge">AIJob</div>
          <h1>管理后台登录</h1>
          <p className="muted">使用管理员账号登录以管理 Local Agent 与任务调度</p>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        <label className="field">
          <span>用户名</span>
          <input
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </label>

        <label className="field">
          <span>密码</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        <button className="btn btn-primary btn-block" type="submit" disabled={loading}>
          {loading ? "登录中..." : "登录"}
        </button>
      </form>
    </div>
  );
}
