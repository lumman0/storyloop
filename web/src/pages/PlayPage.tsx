import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Clock3, Feather, Moon, Plus, Send, Sparkles } from "lucide-react";
import { api, type History, type StorySegment, type View } from "../lib/api";
import { errorMessage } from "../lib/session";
import { Button } from "../components/ui/button";
import { Loading, Notice } from "../components/Feedback";
import { StoryContent } from "../components/StoryContent";
import { ChoicePanel } from "../components/ChoicePanel";
import { containsStoryCommand, isStoryCommandInput, playerFacingText } from "../lib/playerText";
import { clearPendingTurn, readPendingTurn, savePendingTurn } from "../lib/pendingTurn";
import { createRequestId } from "../lib/requestId";

function playerAction(text: string | null, previous: View | null | undefined) {
  if (!text) return "早期存档的行动记录不可用";
  if (text === "/next") return "推进到下一时段";
  if (text === "/rest") return "休息到第二天";
  if (text.startsWith("/choose ")) {
    const [, id, ...rest] = text.split(/\s+/);
    const label = previous?.interaction?.options.find(
      (item) => item.id === id,
    )?.label;
    return label
      ? `选择「${playerFacingText(label)}」${rest.length ? ` · ${playerFacingText(rest.join(" "))}` : ""}`
      : "完成剧情选择";
  }
  return playerFacingText(text);
}

type PendingTurn = {
  id: string;
  text: string;
  stage: string;
  segments: StorySegment[];
  body: string;
  error: string;
  startedAt: number;
};

const stageLabels: Record<string, string> = {
  received: "行动已送达",
  campaign: "检查当前剧情",
  thinking: "理解你的行动",
  committing: "记录世界变化",
  characters: "角色正在回应",
  background: "处理背景事件",
  narrating: "整理本轮故事",
  scene: "铺陈当前场景",
  guidance: "准备后续建议",
};

export function PlayPage() {
  const { gameId = "" } = useParams();
  const [history, setHistory] = useState<History | null>(null);
  const [current, setCurrent] = useState<View | null>(null);
  const [title, setTitle] = useState("正在载入故事");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [pending, setPending] = useState<PendingTurn | null>(null);
  const [now, setNow] = useState(Date.now());
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  useEffect(() => {
    let active = true;
    const savedPending = readPendingTurn(gameId);
    setLoading(true);
    setError("");
    Promise.all([api.saves(), api.resume(gameId)])
      .then(async ([saveList, view]) => {
        const transcript = await api.history(gameId);
        if (!active) return;
        setTitle(
          saveList.saves.find((save) => save.game_id === gameId)?.title ||
            "我的故事",
        );
        setHistory(transcript);
        setCurrent(view);
        if (savedPending && transcript.turns.some((turn) => turn.request_id === savedPending.id)) {
          clearPendingTurn(gameId);
          setPending(null);
        } else {
          setPending(savedPending ? {
            ...savedPending, stage: "received", segments: [], body: "",
            error: "上次行动的结果尚未确认。请用原请求重试。", startedAt: Date.now(),
          } : null);
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
  }, [gameId, retry]);

  useEffect(() => {
    if (history?.turns.length || pending)
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history?.turns.length, pending?.stage, pending?.segments.length]);

  async function submitText(text: string): Promise<boolean> {
    if (!text.trim() || busy || (current?.complete && !pending?.error)) return false;
    if (pending && (!pending.error || pending.text !== text)) return false;
    setError("");
    let requestId: string;
    try {
      requestId = pending?.id ?? createRequestId();
    } catch {
      setError("浏览器无法生成请求标识，请刷新页面后重试。");
      return false;
    }
    setBusy(true);
    savePendingTurn(gameId, { id: requestId, text });
    setPending({
      id: requestId, text, stage: "received", segments: [], body: "", error: "",
      startedAt: Date.now(),
    });
    if (!isStoryCommandInput(text)) setDraft("");
    try {
      const response = await api.turnStream(gameId, text, requestId, (event) => {
        setPending((previous) => {
          if (!previous || previous.id !== requestId) return previous;
          if (event.type === "stage") return { ...previous, stage: event.stage };
          if (event.type === "segment")
            return { ...previous, segments: [...previous.segments, event.segment] };
          if (event.type === "preview")
            return { ...previous, segments: event.segments, body: event.body };
          return previous;
        });
      });
      setHistory((previous) =>
        previous
          ? {
              ...previous,
              turns: previous.turns.some((turn) => turn.request_id === requestId)
                ? previous.turns
                : [...previous.turns, { request_id: requestId, input: text, response }],
            }
          : previous,
      );
      setCurrent(response);
      window.dispatchEvent(new Event("story:billing-updated"));
      clearPendingTurn(gameId);
      setPending(null);
      return true;
    } catch (cause) {
      setPending((previous) => previous?.id === requestId
        ? { ...previous, error: errorMessage(cause) } : previous);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await submitText(draft.trim());
  }

  function useSuggestion(text: string) {
    setDraft(text);
    document.getElementById("turn-input")?.focus();
  }

  const intro = history?.intro;
  const visibleSuggestions = current?.suggestions.filter(
    (suggestion) => !containsStoryCommand(suggestion),
  ) ?? [];

  return (
    <main className="reader-shell">
      <div className="reader-top">
        <Link to="/saves" className="back-link">
          <ArrowLeft size={17} />
          返回存档
        </Link>
        <span className="reader-top-meta">
          {current?.day
            ? `第 ${current.day} 天${current.time_of_day ? ` · ${current.time_of_day}` : ""}`
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
                    {intro.opening && (
                      <div className="story-prose">
                        <p>{playerFacingText(intro.opening)}</p>
                      </div>
                    )}
                    <StoryContent view={intro} />
                  </div>
                </article>
              )}
              {history.turns.map((turn, index) => (
                <div className="turn-pair" key={turn.request_id}>
                  <article className="player-entry">
                    <span className="player-entry-label">
                      你的行动 · {index + 1}
                    </span>
                    <p>
                      {playerAction(
                        turn.input,
                        index === 0
                          ? intro
                          : (history.turns[index - 1]?.response ?? null),
                      )}
                    </p>
                  </article>
                  <article className="story-entry">
                    <div className="entry-marker">
                      <Feather size={17} />
                    </div>
                    <div className="entry-content">
                      <span className="entry-label">故事回应</span>
                      <StoryContent view={turn.response} />
                      {turn.response.billing && (
                        <div className="turn-billing">
                          消耗 {turn.response.billing.charged_points} 积分
                          <span>·</span>
                          输入 {turn.response.billing.input_tokens.toLocaleString()} / 输出 {turn.response.billing.output_tokens.toLocaleString()} Token
                        </div>
                      )}
                    </div>
                  </article>
                </div>
              ))}
              {pending && (
                <div className="turn-pair pending-turn">
                  <article className="player-entry">
                    <span className="player-entry-label">你的行动 · {history.turns.length + 1}</span>
                    <p>{playerAction(pending.text, current)}</p>
                  </article>
                  <article className="story-entry" aria-live="polite">
                    <div className="entry-marker"><Feather size={17} /></div>
                    <div className="entry-content">
                      <span className="entry-label">故事回应</span>
                      <div className={`turn-status ${pending.error ? "turn-status-error" : ""}`} role="status">
                        <span className="status-pulse" aria-hidden="true" />
                        <span>{pending.error || stageLabels[pending.stage] || "故事正在继续"}</span>
                        {!pending.error && (
                          <time>{Math.max(0, Math.floor((now - pending.startedAt) / 1000))} 秒</time>
                        )}
                      </div>
                      {(pending.segments.length > 0 || pending.body) && (
                        <StoryContent view={{ ...current, body: pending.body, segments: pending.segments }} />
                      )}
                      {pending.error && (
                        <div className="pending-actions">
                          <Button type="button" onClick={() => void submitText(pending.text)}>重试这条行动</Button>
                        </div>
                      )}
                    </div>
                  </article>
                </div>
              )}
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
            {!current.complete && current.interaction ? (
              <ChoicePanel
                key={current.interaction.id}
                interaction={current.interaction}
                busy={busy || !!pending}
                onChoose={submitText}
                error={error}
              />
            ) : (
              !current.complete && (
                <form className="composer" onSubmit={submit}>
                  <label htmlFor="turn-input">写下你的行动或想说的话</label>
                  <div className="composer-field">
                    <textarea
                      id="turn-input"
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      placeholder="此刻，你想做什么？"
                      rows={3}
                      maxLength={10000}
                      disabled={busy || !!pending || current.complete}
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
                      disabled={busy || !!pending || !draft.trim() || current.complete}
                    >
                      <Send size={18} />
                    </Button>
                  </div>
                  <div className="composer-hint">
                    <span>Enter 发送 · Shift + Enter 换行</span>
                    <span>
                      {busy ? "世界正在回应…" : `${draft.length}/10000`}
                    </span>
                  </div>
                  {current.mode === "campaign" && (
                    <div className="time-actions" role="group" aria-label="时间操作">
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => void submitText("/next")}
                        disabled={busy || !!pending}
                      >
                        <Clock3 size={17} />
                        推进时段
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => void submitText("/rest")}
                        disabled={busy || !!pending}
                      >
                        <Moon size={17} />
                        休息到次日
                      </Button>
                    </div>
                  )}
                  {error && (
                    <p className="form-error" role="alert">
                      {error}
                    </p>
                  )}
                </form>
              )
            )}
          </section>
          <aside className="reader-aside" aria-label="进度与建议">
            <div className="aside-panel">
              <span className="aside-kicker">当前进度</span>
              <div className="progress-value">
                {current.day
                  ? `第 ${current.day} 天${current.time_of_day ? ` · ${current.time_of_day}` : ""}`
                  : `第 ${current.tick} 回合`}
              </div>
              <p>世界仍在继续运转。</p>
            </div>
            <div className="aside-panel suggestion-panel">
              <div className="aside-heading">
                <Sparkles size={18} />
                <h2>接下来可以试试</h2>
              </div>
              {!current.interaction && visibleSuggestions.length ? (
                <ul>
                  {visibleSuggestions.map((suggestion, index) => (
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
                <p>
                  {current.interaction
                    ? "先完成当前剧情选择，故事就会继续。"
                    : "自由说出你的想法，故事会回应你。"}
                </p>
              )}
              <small>建议只是灵感，行动由你决定。</small>
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}
