import { useEffect, useState } from "react";
import { UserRound } from "lucide-react";
import { api, type PlayerCard } from "../lib/api";
import { errorMessage } from "../lib/session";

const fieldLabels: Record<string, string> = {
  age: "年龄",
  university: "学校",
  school: "学校",
  hometown: "家乡",
  city: "城市",
  major: "专业",
  education: "学历",
  degree: "学历",
  occupation: "职业",
  profession: "职业",
  appearance: "外貌气质",
  temperament: "气质",
  personality: "性格",
  personality_traits: "性格",
  hobbies: "爱好",
  interests: "兴趣",
  talent: "才艺",
  talents: "才艺",
  skills: "擅长",
  background: "背景",
};

function fieldLabel(key: string): string {
  return fieldLabels[key] || key.replace(/[_-]+/g, " ");
}

export function usePlayerCard(gameId: string, stateVersion: number) {
  const [card, setCard] = useState<PlayerCard | null>(null);
  const [loadedGameId, setLoadedGameId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api.playerCard(gameId).then((value) => {
      if (active) {
        setCard(value);
        setLoadedGameId(gameId);
      }
    }).catch((cause) => {
      if (active) {
        setCard(null);
        setLoadedGameId(gameId);
        setError(errorMessage(cause));
      }
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [gameId, stateVersion, retry]);

  return {
    card: loadedGameId === gameId ? card : null,
    loading: loading || loadedGameId !== gameId,
    error: loadedGameId === gameId ? error : "",
    retry: () => setRetry((value) => value + 1),
  };
}

export function PlayerCardPanel({ card, loading, error, onRetry }: {
  card: PlayerCard | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
}) {
  if (!loading && !error && !card?.name && !card?.fields.length) return null;

  return (
    <section className="aside-panel player-card-panel" aria-label="你的角色卡">
      <span className="aside-kicker">你的角色</span>
      {loading && !card && <p role="status">正在读取角色卡…</p>}
      {error && <div className="cast-detail-error" role="alert">
        <p>角色卡暂时无法读取：{error}</p>
        <button type="button" onClick={onRetry}>重试</button>
      </div>}
      {card && (
        <>
          <div className="player-card-heading">
            <span className="player-card-avatar"><UserRound size={23} aria-hidden="true" /></span>
            <div>
              <strong>{card.name || "未命名的主角"}</strong>
              <small>本次旅程的主角</small>
            </div>
          </div>
          {!!card.fields.length && <dl className="player-card-fields">
            {card.fields.map(({ key, value }) => <div key={key}>
              <dt>{fieldLabel(key)}</dt>
              <dd>{value}</dd>
            </div>)}
          </dl>}
        </>
      )}
    </section>
  );
}
