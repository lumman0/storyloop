import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import type { Interaction } from "../lib/api";
import { Button } from "./ui/button";
import { playerFacingText } from "../lib/playerText";

export function ChoicePanel({
  interaction,
  busy,
  onChoose,
  error,
}: {
  interaction: Interaction;
  busy: boolean;
  onChoose: (text: string) => Promise<boolean>;
  error: string;
}) {
  const [selected, setSelected] = useState("");
  const [note, setNote] = useState("");
  useEffect(() => {
    setSelected("");
    setNote("");
  }, [interaction.id]);
  const option = interaction.options.find((item) => item.id === selected);

  if (interaction.kind === "continue") {
    return (
      <div className="choice-panel continue-panel" aria-label="继续阅读剧情">
        <p className="continue-prompt">{playerFacingText(interaction.prompt)}</p>
        <Button type="button" disabled={busy} onClick={() => void onChoose("/continue")}>
          {busy ? "正在继续…" : playerFacingText(interaction.label || "继续阅读")}
          <ArrowRight size={16} />
        </Button>
        {error && <p className="form-error" role="alert">{error}</p>}
      </div>
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (
      !option ||
      !option.enabled ||
      (option.requires_text && !note.trim()) ||
      busy
    )
      return;
    const sent = await onChoose(
      `/choose ${option.id}${note.trim() ? ` ${note.trim()}` : ""}`,
    );
    if (sent) setNote("");
  }

  return (
    <form className="choice-panel" onSubmit={submit} aria-label="当前剧情选择">
      <div className="choice-heading">
        <span>剧情选择</span>
        <h2>{playerFacingText(interaction.prompt)}</h2>
      </div>
      <div
        className="choice-options"
        role="group"
        aria-label={playerFacingText(interaction.prompt)}
      >
        {interaction.options.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={selected === item.id}
            className={
              selected === item.id ? "choice-option selected" : "choice-option"
            }
            disabled={busy || !item.enabled}
            onClick={() => {
              setSelected(item.id);
              setNote("");
            }}
          >
            <span>{playerFacingText(item.label)}</span>
            <span aria-hidden="true">{selected === item.id ? "●" : "○"}</span>
          </button>
        ))}
      </div>
      {interaction.kind === "message" &&
        !interaction.options.some(
          (item) => item.enabled && item.id !== "skip",
        ) && (
          <p className="choice-help">
            还没有可以留言的嘉宾；可以选择暂不发送。
          </p>
        )}
      {option && option.id !== "skip" && (
        <label className="choice-note">
          {option.requires_text ? "写下你的留言" : "想补充的话（可选）"}
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder={
              option.requires_text
                ? "说出你想让对方知道的事…"
                : "也可以直接确认选择"
            }
            rows={3}
            maxLength={10000}
            disabled={busy}
            required={option.requires_text}
          />
        </label>
      )}
      <Button
        type="submit"
        disabled={!option || busy || (option.requires_text && !note.trim())}
      >
        {busy ? "正在继续…" : "确认选择"}
        <ArrowRight size={16} />
      </Button>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
