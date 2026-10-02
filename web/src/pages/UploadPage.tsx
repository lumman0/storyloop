import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, FileArchive, FileUp, LockKeyhole } from "lucide-react";
import { api, type UserScenario } from "../lib/api";
import { errorMessage } from "../lib/session";
import { Button } from "../components/ui/button";
import { Loading, Notice } from "../components/Feedback";

const MAX_FILE_BYTES = 4 * 1024 * 1024;

export function UploadPage() {
  const [scenarios, setScenarios] = useState<UserScenario[]>([]);
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    api.myScenarios()
      .then((result) => { if (active) { setScenarios(result.scenarios); setLoadError(""); } })
      .catch((cause) => { if (active) setLoadError(errorMessage(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [reload]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    if (!file || !file.name.toLowerCase().endsWith(".zip")) {
      setError("请选择 ZIP 格式的剧本包。");
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setError("ZIP 文件不能超过 4 MiB。");
      return;
    }
    setBusy(true);
    try {
      const result = await api.uploadScenario(title.trim(), summary.trim(), file);
      setScenarios((current) => [result, ...current]);
      setTitle("");
      setSummary("");
      setFile(null);
      const input = document.getElementById("scenario-file") as HTMLInputElement | null;
      if (input) input.value = "";
      setSuccess("剧本已保存为私有草稿。检查无误后可以发布给自己试玩。");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function publish(id: string) {
    setBusyId(id);
    setError("");
    setSuccess("");
    try {
      await api.publishScenario(id);
      setReload((value) => value + 1);
      setSuccess("已发布为仅自己可见的可玩剧本。");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusyId(null);
    }
  }

  async function submit(id: string) {
    setBusyId(id);
    setError(""); setSuccess("");
    try {
      await api.submitScenario(id);
      setSuccess("已提交公开审核。审核员只会查看这次提交的剧本版本。");
      setReload((value) => value + 1);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusyId(null); }
  }

  async function withdraw(id: string) {
    setBusyId(id);
    setError(""); setSuccess("");
    try {
      await api.withdrawSubmission(id);
      setSuccess("已撤回审核申请。修改后可上传新版本。");
      setReload((value) => value + 1);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusyId(null); }
  }

  async function uploadVersion(item: UserScenario, file: File | null) {
    if (!file) return;
    setBusyId(item.id);
    setError(""); setSuccess("");
    try {
      await api.uploadScenarioVersion(item.id, item.title, item.summary, file);
      setSuccess("新版本已保存。确认后可以重新提交审核。");
      setReload((value) => value + 1);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setBusyId(null); }
  }

  async function play(id: string) {
    setBusyId(id);
    setError("");
    try {
      const view = await api.createSave(id);
      navigate(`/play/${view.game_id}`);
    } catch (cause) {
      setError(errorMessage(cause));
      setBusyId(null);
    }
  }

  async function removeDraft(id: string) {
    if (!window.confirm("确定删除这个草稿吗？删除后无法恢复。")) return;
    setBusyId(id);
    setError("");
    setSuccess("");
    try {
      await api.deleteScenarioDraft(id);
      setScenarios((current) => current.filter((item) => item.id !== id));
      setSuccess("草稿已删除，可以重新上传剧本包。");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="page-container upload-page">
      <header className="page-title">
        <span className="section-label">作者空间</span>
        <h1>我的剧本</h1>
        <p>上传并私有试玩剧本，也可以提交一个固定版本申请进入公共目录。</p>
      </header>
      <div className="upload-layout">
        <section className="upload-panel" aria-labelledby="upload-heading">
          <div className="upload-panel-heading">
            <FileUp size={22} aria-hidden="true" />
            <div>
              <h2 id="upload-heading">上传剧本包</h2>
              <p>先保存为草稿；私有发布后可以试玩。</p>
            </div>
          </div>
          <form onSubmit={upload} className="upload-form">
            <label htmlFor="scenario-title">剧本名称</label>
            <input id="scenario-title" value={title} maxLength={80} required
              onChange={(event) => setTitle(event.target.value)} placeholder="例如：雪夜来信" />
            <label htmlFor="scenario-summary">简介 <span>选填</span></label>
            <textarea id="scenario-summary" value={summary} maxLength={300} rows={3}
              onChange={(event) => setSummary(event.target.value)}
              placeholder="用一两句话介绍这个故事" />
            <label htmlFor="scenario-file">ZIP 文件</label>
            <input id="scenario-file" type="file" accept=".zip,application/zip" required
              onChange={(event) => setFile(event.target.files?.[0] || null)} />
            <p className="upload-hint">包根目录需有 manifest.json 和世界书 JSON；章节剧本另需 campaign.json。最多 4 MiB，解压后最多 8 MiB。</p>
            <Button type="submit" disabled={busy}>{busy ? "正在校验并保存…" : "上传为私有草稿"}</Button>
          </form>
          <p className="upload-privacy"><LockKeyhole size={15} aria-hidden="true" /> 未通过公开审核的版本不会出现在其他玩家的目录中。</p>
        </section>
        <section className="upload-list" aria-labelledby="upload-list-heading">
          <div className="upload-list-heading">
            <div>
              <span className="section-label">已保存</span>
              <h2 id="upload-list-heading">你的剧本</h2>
            </div>
            <span>{scenarios.length} 个</span>
          </div>
          {error && <Notice message={error} />}
          {success && <p className="upload-success" role="status">{success}</p>}
          {loading ? <Loading label="正在读取你的剧本…" /> : loadError ? (
            <Notice message={loadError} onRetry={() => { setLoading(true); setReload((value) => value + 1); }} />
          ) : scenarios.length ? (
            <div className="upload-items">
              {scenarios.map((item) => (
                <article className="upload-item" key={item.id}>
                  <div className="upload-item-icon"><FileArchive size={21} aria-hidden="true" /></div>
                  <div className="upload-item-body">
                    <div className="upload-item-title">
                      <h3>{item.title}</h3>
                      <span className={item.status === "published" ? "upload-status published" : "upload-status"}>
                        {item.public_state === "active" ? "公开可玩" : item.review_status === "pending" ? "公开审核中"
                          : item.review_status === "rejected" ? "审核未通过"
                          : item.status === "published" ? "私有试玩" : "私有草稿"}
                      </span>
                    </div>
                    {item.summary && <p>{item.summary}</p>}
                    <small>{item.mode === "campaign" ? "章节故事" : "自由探索"} · 包版本 {item.package_version}</small>
                    {item.review_reason && <p className="upload-review-note">审核意见：{item.review_reason}</p>}
                    <div className="upload-item-actions">
                      {item.status === "draft" && (
                        <Button type="button" size="small" onClick={() => publish(item.id)} disabled={busyId !== null}>
                          {busyId === item.id ? "处理中…" : "开启私有试玩"}
                        </Button>
                      )}
                      {item.status === "published" && (
                        <Button type="button" size="small" variant="secondary" onClick={() => play(item.id)} disabled={busyId !== null}>
                          {busyId === item.id ? "正在进入…" : "开始试玩"} <ArrowRight size={15} />
                        </Button>
                      )}
                      {!item.review_status && (
                        <Button type="button" size="small" variant="secondary" onClick={() => submit(item.id)} disabled={busyId !== null}>
                          提交公开审核
                        </Button>
                      )}
                      {item.review_status === "pending" && item.submission_id && (
                        <Button type="button" size="small" variant="ghost" onClick={() => withdraw(item.submission_id!)} disabled={busyId !== null}>
                          撤回申请
                        </Button>
                      )}
                      <input type="file" accept=".zip,application/zip" id={`version-${item.id}`}
                        className="visually-hidden" disabled={busyId !== null}
                        onChange={(event) => { void uploadVersion(item, event.target.files?.[0] || null); event.target.value = ""; }} />
                      <Button type="button" size="small" variant="ghost" disabled={busyId !== null}
                        onClick={() => document.getElementById(`version-${item.id}`)?.click()}>
                        上传新版本
                      </Button>
                      {item.status === "draft" && !item.review_status && (
                        <Button type="button" size="small" variant="ghost" onClick={() => removeDraft(item.id)} disabled={busyId !== null}>
                          删除草稿
                        </Button>
                      )}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="upload-empty">还没有剧本。选择一个 ZIP 剧本包，上传后会先保存为私有草稿。</div>
          )}
        </section>
      </div>
    </main>
  );
}
