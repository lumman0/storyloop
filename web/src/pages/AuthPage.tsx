import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { api, type Session } from "../lib/api";
import { errorMessage } from "../lib/session";
import { Brand } from "../components/Brand";
import { Button } from "../components/ui/button";

export function AuthPage({
  onSession,
}: {
  onSession: (session: Session) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const session =
        mode === "login"
          ? await api.login(username, password)
          : await api.register(username, password, inviteCode.trim());
      onSession(session);
      navigate("/", { replace: true });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-world">
        <div className="auth-world-inner">
          <Brand light />
          <div className="auth-story">
            <span className="auth-issue">一个选择，开启一个世界</span>
            <h1>
              故事会记住
              <br />
              <em>你的每一步。</em>
            </h1>
            <p>
              走进一个会回应你、也会自行向前的世界。与角色相遇，留下自己的故事。
            </p>
            <div className="auth-orbit" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          </div>
          <div className="auth-footnote">STORYLOOP / INTERACTIVE WORLDS</div>
        </div>
      </div>
      <main className="auth-form-side">
        <div className="auth-form-wrap">
          <div className="auth-mobile-brand">
            <Brand />
          </div>
          <span className="section-label">欢迎来到 Storyloop</span>
          <h2>{mode === "login" ? "继续你的故事" : "从这里开始"}</h2>
          <p className="auth-subtitle">
            {mode === "login"
              ? "登录后，回到上次离开的那一页。"
              : "创建账号，开启你的第一段旅程。"}
          </p>
          <div className="auth-tabs" role="tablist" aria-label="账号操作">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "login"}
              className={mode === "login" ? "active" : ""}
              onClick={() => {
                setMode("login");
                setError("");
              }}
            >
              登录
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "register"}
              className={mode === "register" ? "active" : ""}
              onClick={() => {
                setMode("register");
                setError("");
              }}
            >
              注册
            </button>
          </div>
          <form onSubmit={submit} className="auth-form">
            <label htmlFor="username">用户名</label>
            <input
              id="username"
              autoComplete="username"
              minLength={2}
              maxLength={32}
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="输入用户名"
            />
            <label htmlFor="password">密码</label>
            <input
              id="password"
              type="password"
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              minLength={8}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="至少 8 位"
            />
            {mode === "register" && (
              <>
                <label htmlFor="invite-code">邀请码（线上内测需要）</label>
                <input
                  id="invite-code"
                  autoComplete="off"
                  maxLength={128}
                  value={inviteCode}
                  onChange={(event) => setInviteCode(event.target.value)}
                  placeholder="本地试玩可留空"
                />
              </>
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" disabled={busy} className="auth-submit">
              {busy ? "请稍候…" : mode === "login" ? "登录并继续" : "创建账号"}{" "}
              <ArrowRight size={17} />
            </Button>
          </form>
          <p className="auth-note">你的每个故事都保存在自己的存档中。</p>
        </div>
      </main>
    </div>
  );
}
