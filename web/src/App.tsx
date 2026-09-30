import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Link,
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Compass,
  Feather,
  LogOut,
  Menu,
  Plus,
  Send,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import {
  api,
  ApiError,
  type Game,
  type History,
  type Save,
  type Session,
  type View,
} from "./lib/api";
import { Button } from "./components/ui/button";

const SESSION_KEY = "storyloop.session";

function readSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Session;
    return value &&
      typeof value.token === "string" &&
      typeof value.player_id === "string"
      ? value
      : null;
  } catch {
    return null;
  }
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) return "登录已失效，请重新登录。";
    return error.message;
  }
  return "连接服务失败。请确认后端已启动，然后重试。";
}

function Brand({ light = false }: { light?: boolean }) {
  return (
    <Link
      to="/"
      className={`brand ${light ? "brand-light" : ""}`}
      aria-label="Storyloop 首页"
    >
      <span className="brand-mark">
        <Feather size={18} strokeWidth={1.8} />
      </span>
      <span>
        storyloop<span className="brand-dot">.</span>
      </span>
    </Link>
  );
}

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [pathname]);
  return null;
}

function AuthPage({ onSession }: { onSession: (session: Session) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
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
          : await api.register(username, password);
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

function Shell({
  children,
  session,
  onLogout,
}: {
  children: ReactNode;
  session: Session;
  onLogout: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  async function logout() {
    try {
      await api.logout(session.token);
    } catch {
      /* clear the local session even when offline */
    }
    onLogout();
    navigate("/login", { replace: true });
  }
  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="header-inner">
          <Brand />
          <nav
            className={menuOpen ? "main-nav open" : "main-nav"}
            aria-label="主导航"
          >
            <NavLink to="/" end onClick={() => setMenuOpen(false)}>
              <Compass size={17} />
              探索故事
            </NavLink>
            <NavLink to="/saves" onClick={() => setMenuOpen(false)}>
              <BookOpen size={17} />
              我的存档
            </NavLink>
            <button type="button" className="mobile-logout" onClick={logout}>
              <LogOut size={17} />
              退出登录
            </button>
          </nav>
          <div className="header-actions">
            <span className="user-avatar" title="已登录玩家">
              <UserRound size={17} />
            </span>
            <button
              type="button"
              className="icon-action logout"
              onClick={logout}
              aria-label="退出登录"
              title="退出登录"
            >
              <LogOut size={18} />
            </button>
            <button
              type="button"
              className="icon-action mobile-menu"
              onClick={() => setMenuOpen(!menuOpen)}
              aria-label={menuOpen ? "关闭菜单" : "打开菜单"}
            >
              {menuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </header>
      {children}
      <footer className="site-footer">
        <span>storyloop. 让故事继续生长。</span>
        <span>选择属于你的下一页</span>
      </footer>
    </div>
  );
}

function Notice({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="notice" role="alert">
      <p>{message}</p>
      {onRetry && (
        <Button variant="secondary" size="small" onClick={onRetry}>
          重试
        </Button>
      )}
    </div>
  );
}

function Loading({ label = "正在翻开故事…" }: { label?: string }) {
  return (
    <div className="loading-state" role="status">
      <span className="loading-glyph">
        <Feather size={27} />
      </span>
      <p>{label}</p>
    </div>
  );
}

function GameArtwork({ theme }: { theme: string }) {
  return (
    <div
      className={`game-art game-art-${theme === "relay" ? "relay" : "harbor"}`}
      aria-hidden="true"
    >
      <div className="art-glow" />
      <div className="art-horizon" />
      <div className="art-orb" />
      <div className="art-structure one" />
      <div className="art-structure two" />
      <div className="art-grain" />
    </div>
  );
}

function GameCard({
  game,
  onStart,
  busy,
}: {
  game: Game;
  onStart: (id: string) => void;
  busy: boolean;
}) {
  return (
    <article className="game-card">
      <GameArtwork theme={game.theme} />
      <div className="game-card-content">
        <span className="game-tag">
          {game.genre || (game.mode === "campaign" ? "章节故事" : "自由探索")}
        </span>
        <div>
          <h3>{game.title}</h3>
          <p>{game.summary || "走进这个世界，写下你的故事。"}</p>
          <Button
            type="button"
            variant="secondary"
            size="small"
            onClick={() => onStart(game.id)}
            disabled={busy}
          >
            开始旅程 <ArrowRight size={16} />
          </Button>
        </div>
      </div>
    </article>
  );
}

function CatalogPage({ token }: { token: string }) {
  const [games, setGames] = useState<Game[]>([]);
  const [saves, setSaves] = useState<Save[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const navigate = useNavigate();
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([api.catalog(token), api.saves(token)])
      .then(([catalog, saveList]) => {
        if (active) {
          setGames(catalog.games);
          setSaves(saveList.saves);
          setError("");
        }
      })
      .catch((cause) => {
        if (active) setError(errorMessage(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, retry]);

  async function start(catalogId: string) {
    setBusyId(catalogId);
    setError("");
    try {
      const view = await api.createSave(token, catalogId);
      navigate(`/play/${view.game_id}`);
    } catch (cause) {
      setError(errorMessage(cause));
      setBusyId(null);
    }
  }

  return (
    <main>
      <section className="home-hero">
        <div className="hero-content">
          <span className="section-label">互动故事 · 由你续写</span>
          <h1>
            走进故事。
            <br />
            <em>留下你的痕迹。</em>
          </h1>
          <p>
            世界不会等在原地，角色也有自己的生活。每一次交谈和行动，都可能改变下一页。
          </p>
          <a className="hero-link" href="#discover">
            探索故事 <ArrowDown size={18} />
          </a>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="hero-moon" />
          <div className="hero-ridge ridge-back" />
          <div className="hero-ridge ridge-front" />
          <div className="hero-window">
            <span />
          </div>
          <div className="hero-stars">
            <i />
            <i />
            <i />
            <i />
            <i />
          </div>
        </div>
      </section>
      <div className="page-container">
        <section id="discover" className="catalog-section">
          <div className="section-heading">
            <div>
              <span className="section-label">发现</span>
              <h2>选择一个世界</h2>
              <p>从这里开始，故事将沿着你的选择展开。</p>
            </div>
            <span className="section-count">
              {games.length.toString().padStart(2, "0")} 个世界
            </span>
          </div>
          {loading ? (
            <Loading />
          ) : error ? (
            <Notice
              message={error}
              onRetry={() => setRetry((value) => value + 1)}
            />
          ) : games.length ? (
            <div className="game-grid">
              {games.map((game) => (
                <GameCard
                  key={game.id}
                  game={game}
                  onStart={start}
                  busy={busyId !== null}
                />
              ))}
            </div>
          ) : (
            <div className="empty-state">
              还没有可玩的故事。请在服务端目录中添加剧本。
            </div>
          )}
        </section>
        {saves.length > 0 && (
          <section className="continue-section">
            <div className="section-heading compact">
              <div>
                <span className="section-label">继续</span>
                <h2>上次看到这里</h2>
              </div>
              <Link to="/saves" className="text-link">
                全部存档 <ArrowRight size={16} />
              </Link>
            </div>
            <div className="continue-list">
              {saves.slice(0, 3).map((save) => (
                <Link
                  key={save.game_id}
                  to={`/play/${save.game_id}`}
                  className="continue-item"
                >
                  <span className="continue-icon">
                    <BookOpen size={22} />
                  </span>
                  <span className="continue-copy">
                    <strong>{save.title}</strong>
                    <small>
                      {save.day ? `第 ${save.day} 天` : `第 ${save.tick} 回合`}{" "}
                      · {save.complete ? "已完结" : "故事进行中"}
                    </small>
                  </span>
                  <ArrowRight size={18} />
                </Link>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

function SavesPage({ token }: { token: string }) {
  const [saves, setSaves] = useState<Save[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .saves(token)
      .then((value) => {
        if (active) {
          setSaves(value.saves);
          setError("");
        }
      })
      .catch((cause) => {
        if (active) setError(errorMessage(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, retry]);
  return (
    <main className="page-container saves-page">
      <div className="page-title">
        <span className="section-label">我的故事</span>
        <h1>所有存档</h1>
        <p>从任何一个停下的地方，继续写下去。</p>
      </div>
      {loading ? (
        <Loading />
      ) : error ? (
        <Notice
          message={error}
          onRetry={() => setRetry((value) => value + 1)}
        />
      ) : saves.length ? (
        <div className="save-list">
          {saves.map((save) => (
            <div className="save-row" key={save.game_id}>
              <div className="save-emblem">
                <BookOpen size={23} />
              </div>
              <div className="save-main">
                <h2>{save.title}</h2>
                <p>
                  {save.day ? `第 ${save.day} 天` : `第 ${save.tick} 回合`}{" "}
                  <span>·</span> {save.complete ? "故事已完结" : "故事进行中"}
                </p>
              </div>
              {save.available ? (
                <Button asChild variant="secondary" size="small">
                  <Link to={`/play/${save.game_id}`}>
                    继续阅读 <ArrowRight size={16} />
                  </Link>
                </Button>
              ) : (
                <span className="unavailable">剧本不可用</span>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <BookOpen size={30} />
          <h2>还没有存档</h2>
          <p>挑一个世界，开启你的第一段故事。</p>
          <Button asChild>
            <Link to="/">
              探索故事 <ArrowRight size={17} />
            </Link>
          </Button>
        </div>
      )}
    </main>
  );
}

function Prose({ text }: { text: string }) {
  return (
    <div className="story-prose">
      {text
        .split(/\n\s*\n/)
        .filter(Boolean)
        .map((paragraph, index) => (
          <p key={index}>{paragraph}</p>
        ))}
    </div>
  );
}

function PlayPage({ token }: { token: string }) {
  const { gameId = "" } = useParams();
  const [history, setHistory] = useState<History | null>(null);
  const [current, setCurrent] = useState<View | null>(null);
  const [title, setTitle] = useState("正在载入故事");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pendingRequest = useRef<{ text: string; id: string } | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([api.saves(token), api.resume(token, gameId)])
      .then(async ([saveList, view]) => {
        const transcript = await api.history(token, gameId);
        if (!active) return;
        setTitle(
          saveList.saves.find((save) => save.game_id === gameId)?.title ||
            "我的故事",
        );
        setHistory(transcript);
        setCurrent(view);
      })
      .catch((cause) => {
        if (active) setError(errorMessage(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, gameId, retry]);

  useEffect(() => {
    if (history?.turns.length)
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history?.turns.length]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy || current?.complete) return;
    setBusy(true);
    setError("");
    const requestId =
      pendingRequest.current?.text === text
        ? pendingRequest.current.id
        : crypto.randomUUID();
    pendingRequest.current = { text, id: requestId };
    try {
      const response = await api.turn(token, gameId, text, requestId);
      setHistory((previous) =>
        previous
          ? {
              ...previous,
              turns: [
                ...previous.turns,
                { request_id: requestId, input: text, response },
              ],
            }
          : previous,
      );
      setCurrent(response);
      setDraft("");
      pendingRequest.current = null;
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  function useSuggestion(text: string) {
    setDraft(text);
    document.getElementById("turn-input")?.focus();
  }
  const intro = history?.intro;

  return (
    <main className="reader-shell">
      <div className="reader-top">
        <Link to="/saves" className="back-link">
          <ArrowLeft size={17} />
          返回存档
        </Link>
        <span className="reader-top-meta">
          {current?.day
            ? `第 ${current.day} 天`
            : `第 ${current?.tick ?? 0} 回合`}
        </span>
      </div>
      {loading ? (
        <Loading label="正在恢复你的故事…" />
      ) : !history || !current ? (
        <Notice
          message={error || "无法读取这个存档。"}
          onRetry={() => setRetry((value) => value + 1)}
        />
      ) : (
        <div className="reader-layout">
          <section className="reading-column" aria-label="故事内容">
            <div className="story-heading">
              <span className="section-label">正在阅读</span>
              <h1>{title}</h1>
              <p>每一页，都因你的选择而不同。</p>
            </div>
            <div className="story-timeline">
              {intro && (intro.opening || intro.body) && (
                <article className="story-entry intro-entry">
                  <div className="entry-marker">
                    <Sparkles size={17} />
                  </div>
                  <div className="entry-content">
                    <span className="entry-label">序章</span>
                    {intro.opening && <Prose text={intro.opening} />}
                    {intro.body && <Prose text={intro.body} />}
                  </div>
                </article>
              )}
              {history.turns.map((turn, index) => (
                <div className="turn-pair" key={turn.request_id}>
                  <article className="player-entry">
                    <span className="player-entry-label">
                      你的行动 · {index + 1}
                    </span>
                    <p>{turn.input || "早期存档的行动记录不可用"}</p>
                  </article>
                  <article className="story-entry">
                    <div className="entry-marker">
                      <Feather size={17} />
                    </div>
                    <div className="entry-content">
                      <span className="entry-label">故事回应</span>
                      <Prose
                        text={
                          turn.response.body || "世界暂时没有给出新的回应。"
                        }
                      />
                    </div>
                  </article>
                </div>
              ))}
              {!intro?.opening && !intro?.body && !history.turns.length && (
                <div className="empty-story">
                  <p>故事从你的第一句话开始。</p>
                </div>
              )}
            </div>
            <div ref={bottomRef} />
            {current.complete && (
              <div className="end-note">
                <Sparkles size={20} />
                <span>这一段故事已经写完。你可以返回目录，开始新的旅程。</span>
              </div>
            )}
            <form className="composer" onSubmit={submit}>
              <label htmlFor="turn-input">写下你的行动或想说的话</label>
              <div className="composer-field">
                <textarea
                  id="turn-input"
                  value={draft}
                  onChange={(event) => {
                    setDraft(event.target.value);
                    if (
                      pendingRequest.current?.text !== event.target.value.trim()
                    )
                      pendingRequest.current = null;
                  }}
                  placeholder="此刻，你想做什么？"
                  rows={3}
                  maxLength={10000}
                  disabled={busy || current.complete}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                />
                <Button
                  type="submit"
                  size="icon"
                  aria-label="发送行动"
                  disabled={busy || !draft.trim() || current.complete}
                >
                  <Send size={18} />
                </Button>
              </div>
              <div className="composer-hint">
                <span>Enter 发送 · Shift + Enter 换行</span>
                <span>{busy ? "世界正在回应…" : `${draft.length}/10000`}</span>
              </div>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
            </form>
          </section>
          <aside className="reader-aside" aria-label="进度与建议">
            <div className="aside-panel">
              <span className="aside-kicker">当前进度</span>
              <div className="progress-value">
                {current.day
                  ? `第 ${current.day} 天`
                  : `第 ${current.tick} 回合`}
              </div>
              <p>世界仍在继续运转。</p>
            </div>
            <div className="aside-panel suggestion-panel">
              <div className="aside-heading">
                <Sparkles size={18} />
                <h2>接下来可以试试</h2>
              </div>
              {current.suggestions.length ? (
                <ul>
                  {current.suggestions.map((suggestion, index) => (
                    <li key={`${index}-${suggestion}`}>
                      <button
                        type="button"
                        onClick={() => useSuggestion(suggestion)}
                        disabled={current.complete}
                      >
                        <span>{suggestion}</span>
                        <Plus size={15} />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>自由说出你的想法，故事会回应你。</p>
              )}
              <small>建议只是灵感，行动由你决定。</small>
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}

export default function App() {
  const [session, setSession] = useState<Session | null>(readSession);
  function updateSession(next: Session | null) {
    if (next) sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
    else sessionStorage.removeItem(SESSION_KEY);
    setSession(next);
  }
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route
          path="/login"
          element={
            session ? (
              <Navigate to="/" replace />
            ) : (
              <AuthPage onSession={(value) => updateSession(value)} />
            )
          }
        />
        <Route
          path="/*"
          element={
            session ? (
              <Shell session={session} onLogout={() => updateSession(null)}>
                <Routes>
                  <Route
                    path="/"
                    element={<CatalogPage token={session.token} />}
                  />
                  <Route
                    path="/saves"
                    element={<SavesPage token={session.token} />}
                  />
                  <Route
                    path="/play/:gameId"
                    element={<PlayPage token={session.token} />}
                  />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Shell>
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
      </Routes>
    </>
  );
}
