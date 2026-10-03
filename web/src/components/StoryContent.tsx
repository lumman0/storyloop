import type { StorySegment, View } from "../lib/api";
import { playerFacingText } from "../lib/playerText";
import { parseStoryInline } from "../lib/storyMarkup";

function Prose({ text }: { text: string }) {
  const displayText = playerFacingText(text);
  return (
    <div className="story-prose">
      {displayText
        .split(/\n\s*\n/)
        .filter(Boolean)
        .map((paragraph, index) => (
          <p key={index}>
            {parseStoryInline(paragraph).map((part, partIndex) => {
              if (part.kind === "emphasis") return <em key={partIndex}>{part.text}</em>;
              if (part.kind === "strong") return <strong key={partIndex}>{part.text}</strong>;
              return part.text;
            })}
          </p>
        ))}
    </div>
  );
}

function Segment({ segment }: { segment: StorySegment }) {
  if (segment.kind === "prompt") return null;
  // Time remains in the save and progress panel; the story presenter weaves
  // its passage into prose instead of printing a mechanical clock message.
  if (segment.kind === "time") return null;
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
      (item) => item.kind !== "prompt" && item.kind !== "time" && item.text.trim(),
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
