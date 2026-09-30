import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BookOpen } from "lucide-react";
import { api, type Save } from "../lib/api";
import { errorMessage } from "../lib/session";
import { Button } from "../components/ui/button";
import { Loading, Notice } from "../components/Feedback";

export function SavesPage({ token }: { token: string }) {
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
