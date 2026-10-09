import { useEffect, useState } from "react";
import { Coins } from "lucide-react";
import { api, type CreditEntry, type CreditWallet } from "../lib/api";
import { errorMessage } from "../lib/session";
import { Loading, Notice } from "../components/Feedback";

function entryTime(value: number) {
  return new Date(value / 1_000_000).toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export function CreditsPage() {
  const [wallet, setWallet] = useState<CreditWallet | null>(null);
  const [entries, setEntries] = useState<CreditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([api.wallet(), api.creditLedger()])
      .then(([balance, ledger]) => {
        if (!active) return;
        setWallet(balance);
        setEntries(ledger.entries);
        setError("");
      })
      .catch((cause) => {
        if (active) setError(errorMessage(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [retry]);

  return (
    <main className="page-container credits-page">
      <div className="page-title">
        <span className="section-label">账户</span>
        <h1>我的积分</h1>
        <p>每次故事回应按本轮实际模型 Token 用量结算。</p>
      </div>
      {loading ? <Loading label="正在读取积分…" /> : error ? (
        <Notice message={error} onRetry={() => setRetry((value) => value + 1)} />
      ) : wallet && (
        <>
          <section className="wallet-summary" aria-label="积分余额">
            <div className="wallet-icon"><Coins size={24} /></div>
            <div>
              <span>当前可用</span>
              <strong>{wallet.balance_points}<small> 积分</small></strong>
              <p>注册赠送 {wallet.welcome_points} 积分。系统按 {wallet.points_per_rmb} 积分对应 ¥1 的基准计算模型消耗。</p>
            </div>
          </section>
          <section className="credit-history" aria-label="积分流水">
            <div className="credit-history-head">
              <h2>最近明细</h2>
              <span>模型输入、输出与缓存用量均计入结算</span>
            </div>
            {entries.length ? entries.map((entry) => (
              <article className="credit-entry" key={entry.entry_id}>
                <div className="credit-entry-main">
                  <div>
                    <strong>{entry.kind === "welcome" ? "注册赠送" : "故事回合"}</strong>
                    <time>{entryTime(entry.created_order)}</time>
                  </div>
                  <div className="credit-entry-value">
                    <strong className={entry.delta_milli_points >= 0 ? "credit-plus" : "credit-minus"}>
                      {entry.delta_milli_points > 0 ? "+" : ""}{entry.delta_points}
                    </strong>
                    <span>余额 {entry.balance_after_points}</span>
                  </div>
                </div>
                {entry.kind === "turn" && (
                  <details>
                    <summary>查看 Token 用量</summary>
                    <div className="credit-usage">
                      {entry.usage_cost_milli_points > -entry.delta_milli_points && (
                        <p>本轮应计 {(entry.usage_cost_milli_points / 1000).toFixed(3)} 积分，余额不足时仅扣除剩余积分。</p>
                      )}
                      {entry.usage.length ? entry.usage.map((call, index) => (
                        <div key={`${entry.entry_id}-${index}`}>
                          <span>{call.model} · {call.task}</span>
                          <span>输入 {call.input_tokens.toLocaleString()} / 输出 {call.output_tokens.toLocaleString()}
                            {call.cached_input_tokens ? ` · 缓存 ${call.cached_input_tokens.toLocaleString()}` : ""}</span>
                        </div>
                      )) : <p>本轮未调用模型。</p>}
                    </div>
                  </details>
                )}
              </article>
            )) : <p className="credit-empty">还没有积分记录。</p>}
          </section>
        </>
      )}
    </main>
  );
}
