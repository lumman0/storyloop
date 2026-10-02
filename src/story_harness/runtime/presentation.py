"""Ordered, player-visible story blocks shared by runtime and portal."""

from __future__ import annotations

from dataclasses import dataclass

from story_harness.adapters.store import GameStore
from story_harness.core.contracts import Observation


@dataclass(frozen=True)
class StorySegment:
    kind: str
    text: str
    speaker_id: str | None = None
    speaker_name: str | None = None

    @property
    def body_text(self) -> str:
        if self.kind == "dialogue" and self.speaker_name:
            return f"【{self.speaker_name}】\n{self.text}"
        return self.text

    def to_dict(self) -> dict[str, str]:
        result = {"kind": self.kind, "text": self.text}
        if self.speaker_id:
            result["speaker_id"] = self.speaker_id
        if self.speaker_name:
            result["speaker_name"] = self.speaker_name
        return result


def segment_for_observation(store: GameStore, game_id: str, item: Observation) -> StorySegment:
    if item.channel != "dialogue":
        kind = "message" if item.channel == "private_message" else "scene" if item.channel == "scene" else "narration"
        return StorySegment(kind, item.content)
    details = store.event_details(game_id, item.event_id) or {}
    speaker_id = details.get("speaker_id")
    speaker_name = details.get("speaker_name")
    speech = details.get("speech")
    if isinstance(speaker_name, str) and isinstance(speech, str):
        return StorySegment("dialogue", speech.strip(),
                            speaker_id if isinstance(speaker_id, str) else None, speaker_name)
    # Older saves have the display label only in the visible observation.
    if item.content.startswith("【") and "】\n" in item.content:
        label, content = item.content[1:].split("】\n", 1)
        return StorySegment("dialogue", content, None, label)
    return StorySegment("dialogue", item.content)
