import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type AuditEvent, type ManagedUser, type PublicRelease,
  type ReviewDetail, type ReviewSubmission, type Session } from "../lib/api";
import { errorMessage } from "../lib/session";
import { Loading, Notice } from "../components/Feedback";
import { Button } from "../components/ui/button";
import { InvitationPanel } from "./InvitationPanel";

type Tab = "reviews" | "users" | "invites" | "releases" | "audit";

export function ManagePage({ session }: { session: Session }) {
  const navigate = useNavigate();
  const admin = session.capabilities.includes("users.manage");
  const [tab, setTab] = useState<Tab>("reviews");
  const [reviews, setReviews] = useState<ReviewSubmission[]>([]);
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [releases, setReleases] = useState<PublicRelease[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    if (tab === "invites") { setLoading(false); return; }
    const request = tab === "reviews" ? api.reviewQueue().then((data) => { if (active) setReviews(data.submissions); })
      : tab === "users" ? api.managedUsers().then((data) => { if (active) setUsers(data.users); })
      : tab === "releases" ? api.publicReleases().then((data) => { if (active) setReleases(data.releases); })
      : api.managementAudit().then((data) => { if (active) setEvents(data.events); });
    request.catch((cause) => { if (active) setError(errorMessage(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [tab, refresh]);

  async function openReview(id: string) {
    setError(""); setDetail(null); setReason("");
    try { setDetail(await api.reviewDetail(id)); }
    catch (cause) { setError(errorMessage(cause)); }
  }

  async function decide(decision: "approved" | "rejected") {
    if (!detail) return;
    if (decision === "rejected" && !reason.trim()) {
      setError("驳回时请写明原因，作者才能修改后提交新版本。"); return;
    }
    setBusy(true); setError("");
    try {
      await api.reviewDecide(detail.submission_id, decision, reason.trim());
      setDetail(null); setReason("");
      setMessage(decision === "approved" ? "该版本已通过审核并进入公共目录。" : "审核意见已送达作者。");
      setRefresh((value) => value + 1);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  async function preview() {
    if (!detail) return;
    setBusy(true); setError("");
    try {
      const view = await api.reviewPreview(detail.submission_id);
      navigate(`/play/${view.game_id}`);
    } catch (cause) { setError(errorMessage(cause)); setBusy(false); }
  }

  async function changeRole(user: ManagedUser, role: "reviewer" | "admin") {
    const enabled = !user.roles.includes(role);
    if (!window.confirm(`${enabled ? "授予" : "撤销"} ${user.username} 的${role === "admin" ? "管理员" : "审核员"}权限？`)) return;
    setBusy(true); setError("");
    try { await api.setRole(user.player_id, role, enabled); setRefresh((value) => value + 1); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  async function changeStatus(user: ManagedUser) {
    const status = user.status === "active" ? "suspended" : "active";
    if (!window.confirm(`${status === "suspended" ? "停用" : "恢复"}账号 ${user.username}？`)) return;
    setBusy(true); setError("");
    try { await api.setAccountStatus(user.player_id, status); setRefresh((value) => value + 1); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  async function changeRelease(release: PublicRelease, state: "active" | "retired" | "blocked") {
    const reason = state === "blocked" ? window.prompt("请填写违规下架原因：") : "";
    if (state === "blocked" && !reason?.trim()) return;
    if (!window.confirm(`将《${release.title}》设为${state === "active" ? "公开" : state === "retired" ? "停止新玩家进入" : "违规下架"}？`)) return;
    setBusy(true); setError("");
    try { await api.setReleaseState(release.scenario_id, state, reason?.trim() || ""); setRefresh((value) => value + 1); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }

  return <main className="page-container manage-page">
    <header className="page-title"><span className="section-label">平台工作台</span>
      <h1>内容与账号管理</h1><p>审核针对固定剧本版本；每项决定都会记录操作者与原因。</p>
    </header>
    <div className="manage-tabs" role="tablist" aria-label="管理功能">
      <button type="button" role="tab" aria-selected={tab === "reviews"} onClick={() => { setTab("reviews"); setDetail(null); }}>审核队列</button>
      {admin && <button type="button" role="tab" aria-selected={tab === "users"} onClick={() => setTab("users")}>用户权限</button>}
      {admin && <button type="button" role="tab" aria-selected={tab === "invites"} onClick={() => setTab("invites")}>邀请码</button>}
      {admin && <button type="button" role="tab" aria-selected={tab === "releases"} onClick={() => setTab("releases")}>公开剧本</button>}
      {admin && <button type="button" role="tab" aria-selected={tab === "audit"} onClick={() => setTab("audit")}>操作记录</button>}
    </div>
    {error && <Notice message={error} />}
    {message && <p className="upload-success" role="status">{message}</p>}
    {loading ? <Loading label="正在读取管理数据…" /> : <>
      {tab === "invites" && <InvitationPanel />}
      {tab === "reviews" && <div className="manage-review-layout">
        <section className="manage-panel"><h2>待审核 · {reviews.length}</h2>
          {reviews.length ? reviews.map((item) => <button className="manage-row-button" type="button" key={item.submission_id}
            onClick={() => void openReview(item.submission_id)}>
            <strong>{item.title}</strong><span>{item.author_name} · {item.mode === "campaign" ? "章节故事" : "自由探索"} · {new Date(item.submitted_at * 1000).toLocaleString()}</span>
          </button>) : <p className="manage-empty">当前没有待审核的剧本。</p>}
        </section>
        <section className="manage-panel manage-detail" aria-live="polite">
          {!detail ? <p className="manage-empty">选择左侧剧本，查看送审时固定的内容和版本。</p> : <>
            <span className="section-label">版本 {detail.package_version}</span><h2>{detail.title}</h2>
            <p>{detail.summary || "作者未填写简介。"}</p>
            <p className="manage-hash">内容指纹：{detail.package_hash}</p>
            <Button size="small" variant="secondary" disabled={busy} onClick={() => void preview()}>隔离试玩预览</Button>
            <p className="manage-preview-note">预览使用审核员自己的临时存档，最多 12 回合；模型费用由平台承担，不扣玩家积分。</p>
            <details open><summary>剧本结构</summary><pre>{JSON.stringify(detail.manifest, null, 2)}</pre></details>
            <details><summary>世界书与角色卡</summary><pre>{JSON.stringify(detail.worldbook, null, 2)}</pre></details>
            {detail.campaign && <details><summary>剧情日程</summary><pre>{JSON.stringify(detail.campaign, null, 2)}</pre></details>}
            <label className="manage-reason-label" htmlFor="review-reason">审核意见；驳回或管理员审核自己的剧本时必填</label>
            <textarea id="review-reason" value={reason} maxLength={1000} rows={3} onChange={(event) => setReason(event.target.value)} />
            <div className="manage-actions">
              <Button disabled={busy} onClick={() => void decide("approved")}>通过并公开</Button>
              <Button disabled={busy} variant="secondary" onClick={() => void decide("rejected")}>驳回</Button>
            </div>
          </>}
        </section>
      </div>}
      {tab === "users" && <section className="manage-panel"><h2>用户与角色</h2>
        {users.map((user) => <div className="manage-list-row" key={user.player_id}>
          <div><strong>{user.username}</strong><span>{user.status === "active" ? "正常" : "已停用"} · {user.roles.join("、") || "玩家"}</span></div>
          <div className="manage-actions">
            <Button size="small" variant="secondary" disabled={busy} onClick={() => void changeRole(user, "reviewer")}>{user.roles.includes("reviewer") ? "撤销审核员" : "设为审核员"}</Button>
            <Button size="small" variant="ghost" disabled={busy} onClick={() => void changeRole(user, "admin")}>{user.roles.includes("admin") ? "撤销管理员" : "设为管理员"}</Button>
            <Button size="small" variant="ghost" disabled={busy} onClick={() => void changeStatus(user)}>{user.status === "active" ? "停用账号" : "恢复账号"}</Button>
          </div>
        </div>)}
      </section>}
      {tab === "releases" && <section className="manage-panel"><h2>公开剧本</h2>
        {releases.length ? releases.map((release) => <div className="manage-list-row" key={release.scenario_id}>
          <div><strong>{release.title}</strong><span>{release.state === "active" ? "公开" : release.state === "retired" ? "停止新玩家进入" : "违规下架"}</span></div>
          <div className="manage-actions">
            {release.state !== "active" && <Button size="small" variant="secondary" disabled={busy} onClick={() => void changeRelease(release, "active")}>恢复公开</Button>}
            {release.state === "active" && <Button size="small" variant="secondary" disabled={busy} onClick={() => void changeRelease(release, "retired")}>停止新玩家进入</Button>}
            {release.state !== "blocked" && <Button size="small" variant="ghost" disabled={busy} onClick={() => void changeRelease(release, "blocked")}>违规下架</Button>}
          </div>
        </div>) : <p className="manage-empty">还没有公开剧本。</p>}
      </section>}
      {tab === "audit" && <section className="manage-panel"><h2>最近操作</h2>
        {events.length ? events.map((event) => <div className="manage-list-row" key={event.event_id}>
          <div><strong>{event.action}</strong><span>{event.actor_id} · {event.target_type}:{event.target_id}</span></div>
          <time>{new Date(event.created_at * 1000).toLocaleString()}</time>
        </div>) : <p className="manage-empty">还没有管理操作。</p>}
      </section>}
    </>}
  </main>;
}
