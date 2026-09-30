import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Feather, Plus, Send, Sparkles } from "lucide-react";
import { api, type History, type View } from "../lib/api";
import { errorMessage } from "../lib/session";
import { Button } from "../components/ui/button";
import { Loading, Notice } from "../components/Feedback";

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

export function PlayPage({ token }: { token: string }) {
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
