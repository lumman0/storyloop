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
) -> Snapshot:
    """A player utterance costs one slot and records only that it was said."""
    if not event_id or not isinstance(text, str) or not text.strip():
        raise ValueError("player input requires an event ID and nonempty text")
    if channel not in {"speech", "private_message"}:
        raise ValueError(f"unsupported player channel: {channel}")
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("duplicate player input target")
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

    tick = before.tick + 1
    event = WorldEvent(
        event_id, "player_input", "player", None, tick, (),
        details={"text": text, "channel": channel, "target_ids": list(target_ids)},
    )
    observations = tuple(
        Observation(
            f"{event_id}:heard:{actor_id}", event_id, actor_id, channel, text, tick
        )
        for actor_id in target_ids
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
