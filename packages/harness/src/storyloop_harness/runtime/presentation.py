"""Ordered, player-visible story blocks shared by runtime and portal."""

from __future__ import annotations

from dataclasses import dataclass

from storyloop_harness.core.store_port import GameStore
from storyloop_harness.core.contracts import Observation, Snapshot
from storyloop_harness.core.turn_result import StorySegment


@dataclass(frozen=True)
class SceneContext:
    """Player-visible beats handed to a replaceable final presenter."""

    game_id: str
    player_text: str
    snapshot: Snapshot
    segments: tuple[StorySegment, ...]
    opening: bool
    day: int
    period: str
    current_goal: str = ""


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
