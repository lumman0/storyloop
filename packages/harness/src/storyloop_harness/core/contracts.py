from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Snapshot:
    game_id: str
    version: int
    tick: int
    data: dict[str, object]


@dataclass(frozen=True)
class Effect:
    path: tuple[str, ...]
    value: object


@dataclass(frozen=True)
class WorldEvent:
    event_id: str
    kind: str
    actor_id: str | None
    cause_id: str | None
    tick: int
    effects: tuple[Effect, ...]
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    observation_id: str
    event_id: str
    recipient_id: str
    channel: str
    content: str
    tick: int


@dataclass(frozen=True)
class PlayerInput:
    event_id: str
    tick: int
    text: str
    channel: str
    target_ids: tuple[str, ...]


@dataclass(frozen=True)
class AgentContextEntry:
    """One committed fact visible to exactly one agent."""

    state_version: int
    entry_id: str
    channel: str
    content: str
    tick: int


@dataclass(frozen=True)
class AgentContextCheckpoint:
    """Persisted compression cursor; source events remain authoritative."""

    through_version: int = -1
    summary: str = ""


@dataclass(frozen=True)
class PendingWork:
    work_id: str
    kind: str
    due_tick: int
    priority: int
    cause_id: str | None
    payload: dict[str, object]
    mandatory: bool = True
