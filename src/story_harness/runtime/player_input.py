"""Persist a player's speech before waking any NPC."""

from __future__ import annotations

from story_harness.core.contracts import Observation, PendingWork, Snapshot, WorldEvent
from story_harness.adapters.store import GameStore


def submit_player_input(
    store: GameStore,
    game_id: str,
    event_id: str,
    text: str,
    target_ids: tuple[str, ...] = (),
    *,
    channel: str = "speech",
    audience: str = "targets",
    duration_ticks: int = 1,
    duration: str = "brief",
) -> Snapshot:
    """Record an utterance and its elapsed world time before waking NPCs."""
    if not event_id or not isinstance(text, str) or not text.strip():
        raise ValueError("player input requires an event ID and nonempty text")
    if channel not in {"speech", "private_message"}:
        raise ValueError(f"unsupported player channel: {channel}")
    if audience not in {"targets", "room"}:
        raise ValueError(f"unsupported speech audience: {audience}")
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("duplicate player input target")
    if type(duration_ticks) is not int or duration_ticks < 0:
        raise ValueError("duration_ticks must be a nonnegative integer")
    before = store.load(game_id)
    actors = before.data.get("actors")
    if not isinstance(actors, dict):
        raise ValueError("player input requires actors state")
    player = actors.get("player")
    if not isinstance(player, dict) or not isinstance(player.get("location"), str):
        raise ValueError("player requires a location")
    for actor_id in target_ids:
        target = actors.get(actor_id)
        if actor_id == "player" or not isinstance(target, dict):
            raise ValueError(f"unknown player input target: {actor_id}")
        if channel == "speech" and target.get("location") != player["location"]:
            raise ValueError("spoken target must share the same location")

    tick = before.tick + duration_ticks
    event = WorldEvent(
        event_id, "player_input", "player", None, tick, (),
        details={"text": text, "channel": channel, "audience": audience,
                 "target_ids": list(target_ids), "before_tick": before.tick,
                 "duration_ticks": duration_ticks, "duration": duration},
    )
    hearer_ids = (
        tuple(actor_id for actor_id, state in actors.items()
              if actor_id != "player" and isinstance(state, dict)
              and state.get("location") == player["location"])
        if channel == "speech" and audience == "room" else target_ids
    )
    observations = tuple(
        Observation(
            f"{event_id}:heard:{actor_id}", event_id, actor_id, channel, text, tick
        )
        for actor_id in hearer_ids
    )
    work = tuple(
        PendingWork(
            f"{event_id}:reply:{actor_id}", "npc_reply", tick, 10,
            event_id,
            {"actor_id": actor_id, "player_message": text, "duration_ticks": 0},
        )
        for actor_id in target_ids
    )
    return store.commit(game_id, before.version, event, observations, work)
