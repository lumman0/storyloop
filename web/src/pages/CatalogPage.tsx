import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowDown, ArrowRight, BookOpen } from "lucide-react";
import { api, type Game, type Save } from "../lib/api";
import { errorMessage } from "../lib/session";
import { Button } from "../components/ui/button";
import { Loading, Notice } from "../components/Feedback";

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
  onStart: (id: string, mode: "campaign" | "freeform") => void;
  busy: boolean;
}) {
  const [selectedMode, setSelectedMode] = useState<"campaign" | "freeform">(game.mode);
  const availableModes = game.play_modes?.length ? game.play_modes : [game.mode];
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
          {availableModes.length > 1 && (
            <div className="game-mode-picker" role="radiogroup" aria-label={`${game.title}游玩模式`}>
              {availableModes.map((mode) => (
                <button type="button" role="radio" aria-checked={selectedMode === mode}
                  className={`game-mode-option ${selectedMode === mode ? "selected" : ""}`}
                  key={mode} disabled={busy} onClick={() => setSelectedMode(mode)}>
                  <strong>{mode === "campaign" ? "小说模式" : "剧本模式"}</strong>
                  <span>{mode === "campaign" ? "以第一人称阅读与选择，主控整合角色回应" : "直接与角色对话，在世界中自由行动"}</span>
                </button>
              ))}
            </div>
          )}
          <Button
            type="button"
            variant="secondary"
            size="small"
            onClick={() => onStart(game.id, selectedMode)}
            disabled={busy}
          >
            开始旅程 <ArrowRight size={16} />
          </Button>
        </div>
      </div>
    </article>
  );
}

export function CatalogPage() {
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
    Promise.all([api.catalog(), api.saves()])
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
  }, [retry]);

  async function start(catalogId: string, playMode: "campaign" | "freeform") {
    setBusyId(catalogId);
    setError("");
    try {
      const view = await api.createSave(catalogId, playMode);
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
                      · {save.mode === "freeform" ? "剧本模式" : "小说模式"}
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
