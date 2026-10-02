import type { StorySegment, View } from "../lib/api";

function Prose({ text }: { text: string }) {
  return (
    <div className="story-prose">
      {text
        .split(/\n\s*\n/)
        .filter(Boolean)
        .map((paragraph, index) => (
          <p key={index}>{paragraph}</p>
        ))}
    </div>
  );
}

function Segment({ segment }: { segment: StorySegment }) {
  if (segment.kind === "prompt") return null;
  if (segment.kind === "dialogue") {
    return (
      <div className="dialogue-block">
        <div className="dialogue-speaker">
          {segment.speaker_name || "在场的人"}
        </div>
        <Prose text={segment.text} />
      </div>
    );
  }
  if (segment.kind === "message") {
    return (
      <div className="message-block">
        <span>私密消息</span>
        <Prose text={segment.text} />
      </div>
    );
  }
  return (
    <div
      className={segment.kind === "scene" ? "scene-block" : "narration-block"}
    >
      <Prose text={segment.text} />
    </div>
  );
}

export function StoryContent({ view }: { view: View }) {
  if (view.segments?.length) {
    const visible = view.segments.filter(
      (item) => item.kind !== "prompt" && item.text.trim(),
    );
    return visible.length ? (
      <div className="story-segments">
        {visible.map((segment, index) => (
          <Segment
            key={`${index}-${segment.speaker_id || segment.kind}`}
            segment={segment}
          />
        ))}
      </div>
    ) : null;
  }
  return view.body ? <Prose text={view.body} /> : null;
}
