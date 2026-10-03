import { type FormEvent, useEffect, useState } from "react";
import { api, type ManagedInvitation } from "../lib/api";
import { errorMessage } from "../lib/session";
import { Loading, Notice } from "../components/Feedback";
import { Button } from "../components/ui/button";

const STATUS_LABEL: Record<ManagedInvitation["status"], string> = {
  available: "待使用", used: "已使用", expired: "已过期", revoked: "已撤销",
};

export function InvitationPanel() {
  const [invites, setInvites] = useState<ManagedInvitation[]>([]);
  const [codes, setCodes] = useState<string[]>([]);
  const [count, setCount] = useState("1");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    api.managedInvitations()
      .then((data) => { if (active) { setInvites(data.invites); setError(""); } })
      .catch((cause) => { if (active) setError(errorMessage(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);

  async function issue(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amount = Number(count);
    if (!Number.isInteger(amount) || amount < 1 || amount > 20) {
      setError("每次可以生成 1 至 20 枚邀请码。"); return;
    }
    setBusy(true); setError(""); setMessage(""); setCodes([]);
    try {
      const result = await api.issueInvitations(amount);
      setCodes(result.codes);
      setMessage(`已生成 ${result.codes.length} 枚邀请码，请现在复制并妥善保存。`);
      setRefresh((value) => value + 1);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  async function copyCodes() {
    try {
      await navigator.clipboard.writeText(codes.join("\n"));
      setMessage("邀请码已复制。每枚只能注册一个账号。");
    } catch { setError("复制失败，请手动选中并复制邀请码。"); }
  }

  async function revoke(invite: ManagedInvitation) {
    if (!window.confirm("撤销这枚未使用的邀请码？撤销后无法恢复。")) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await api.revokeInvitation(invite.id);
      setMessage("邀请码已撤销。");
      setRefresh((value) => value + 1);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  return <section className="manage-panel manage-invites">
    <h2>内测邀请码</h2>
    <p className="manage-empty">当前由管理员发放。每枚邀请码只能注册一次，有效期 30 天。公测时再开放给完成首次游玩的账号。</p>
    {error && <Notice message={error} />}
    {message && <p className="upload-success" role="status">{message}</p>}
    <form className="manage-invite-form" onSubmit={(event) => void issue(event)}>
      <label htmlFor="invite-count">生成数量</label>
      <input id="invite-count" type="number" min="1" max="20" step="1" value={count}
        onChange={(event) => setCount(event.target.value)} />
      <Button type="submit" disabled={busy}>{busy ? "正在生成…" : "生成邀请码"}</Button>
    </form>
    {codes.length > 0 && <div className="manage-issued-codes">
      <strong>本次生成的邀请码</strong>
      <p>明文只在本次页面显示；关闭或刷新后无法再次查看。</p>
      <textarea readOnly rows={Math.min(codes.length + 1, 10)} aria-label="本次生成的邀请码"
        value={codes.join("\n")} onFocus={(event) => event.currentTarget.select()} />
      <div className="manage-actions">
        <Button size="small" type="button" onClick={() => void copyCodes()}>复制全部</Button>
        <Button size="small" type="button" variant="ghost" onClick={() => setCodes([])}>已保存，隐藏</Button>
      </div>
    </div>}
    <h3>发放记录</h3>
    {loading ? <Loading label="正在读取邀请码…" /> : invites.length ? invites.map((invite) =>
      <div className="manage-list-row" key={invite.id}>
        <div><strong>{STATUS_LABEL[invite.status]}</strong>
          <span>{invite.issuer_name || "服务器"} 发放 · 到期 {new Date(invite.expires_at * 1000).toLocaleString()}</span>
          {invite.used_name && <span>注册账号：{invite.used_name}</span>}
        </div>
        {invite.status === "available" && <Button size="small" type="button" variant="ghost"
          disabled={busy} onClick={() => void revoke(invite)}>撤销</Button>}
      </div>) : <p className="manage-empty">暂无邀请码记录。</p>}
  </section>;
}
