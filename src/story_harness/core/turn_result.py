"""Shared results and player-visible story segments."""

from __future__ import annotations

from dataclasses import dataclass

from story_harness.core.contracts import Observation, Snapshot
from story_harness.core.decisions import MainDecision


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


@dataclass(frozen=True)
class TurnOutcome:
    decision: MainDecision
    narration: str
    player_observations: tuple[Observation, ...]
    processed_work_ids: tuple[str, ...]
    snapshot: Snapshot
    narration_fallback: bool = False
    segments: tuple[StorySegment, ...] = ()
