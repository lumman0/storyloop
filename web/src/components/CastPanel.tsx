import { useEffect, useState } from "react";
import { ChevronDown, UserRound } from "lucide-react";
import { api, type CastMember, type CharacterDetail } from "../lib/api";
import { errorMessage } from "../lib/session";

export function CastPanel({ cast, gameId, stateVersion }: {
  cast: CastMember[];
  gameId: string;
  stateVersion: number;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CharacterDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    setSelectedId(null);
    setDetail(null);
  }, [gameId]);

  useEffect(() => {
    if (!selectedId || !cast.some((member) => member.id === selectedId)) {
      setDetail(null);
      return;
    }
    let active = true;
    setLoading(true);
    setError("");
    api.characterDetail(gameId, selectedId).then((value) => {
      if (active) setDetail(value);
    }).catch((cause) => {
      if (active) {
        setDetail(null);
        setError(errorMessage(cause));
      }
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [gameId, selectedId, stateVersion, retry, cast]);

  if (!cast.length) return null;
  return (
    <div className="aside-panel cast-panel">
      <span className="aside-kicker">已经认识的人</span>
      <div className="cast-grid">
        {cast.map((member) => (
          <button type="button" className={`cast-member ${selectedId === member.id ? "selected" : ""}`}
            key={member.id} aria-expanded={selectedId === member.id}
            aria-controls={selectedId === member.id ? "cast-detail" : undefined}
            onClick={() => setSelectedId(selectedId === member.id ? null : member.id)}>
            {member.portrait_url
              ? <img src={member.portrait_url} alt="" loading="lazy" />
              : <span className="cast-avatar-fallback"><UserRound size={19} /></span>}
            <span className="cast-member-name">{member.name}</span>
            <ChevronDown className="cast-chevron" size={14} aria-hidden="true" />
          </button>
        ))}
      </div>
      {selectedId && (
        <div className="cast-detail" id="cast-detail" role="region"
          aria-label={`${cast.find((member) => member.id === selectedId)?.name || "角色"}的人物卡`}>
          {loading && <p className="cast-detail-loading">正在读取人物卡…</p>}
          {error && <div className="cast-detail-error"><p>{error}</p>
            <button type="button" onClick={() => setRetry((value) => value + 1)}>重试</button>
          </div>}
          {!loading && !error && detail && (
            <>
              <div className="cast-detail-header">
                {detail.portrait_url
                  ? <img src={detail.portrait_url} alt="" />
                  : <span className="cast-avatar-fallback"><UserRound size={28} /></span>}
                <div><strong>{detail.name}</strong><span>人物卡</span></div>
              </div>
              <p className="cast-profile">{detail.profile || "还没有公开的人物介绍；你可以在故事中继续了解。"}</p>
              <div className="cast-relationship">
                <span>你们的关系</span>
                <strong>{detail.affinity === null ? "尚无关系数值" : `关系值 ${detail.affinity}`}</strong>
                <small>共同经历 {detail.shared_event_count} 件事</small>
              </div>
              <div className="cast-memories">
                <span>共同记忆</span>
                {detail.memories.length
                  ? <ul>{detail.memories.map((memory, index) => <li key={`${index}-${memory}`}>{memory}</li>)}</ul>
                  : <p>你们还没有留下可共同回忆的事。</p>}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
