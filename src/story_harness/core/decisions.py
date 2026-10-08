"""Shared structured player-turn decision."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MainDecision(BaseModel):
    intent: Literal["speech", "inspect", "action"]
    duration: Literal["brief", "standard", "extended", "rest"] = "brief"
    target_ids: list[str] = Field(default_factory=list)
    channel: Literal["speech", "private_message"] = "speech"
    audience: Literal["targets", "room"] = "targets"
    entry_id: str | None = None
    action_id: str | None = None
