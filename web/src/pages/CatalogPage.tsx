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

export function CatalogPage({ token }: { token: string }) {
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
