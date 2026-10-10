"""Player-safe projection of an NPC's committed context."""

from __future__ import annotations

from storyloop_harness import GameStore


def shared_actor_memories(store: GameStore, game_id: str, actor_id: str,
                          limit: int = 4) -> tuple[int, list[str]]:
    """Only include events both the NPC and player actually observed.

    NPC compression checkpoints may contain private knowledge. Their raw text
    must never become part of a player-facing character card.
    """
    actor_events = {item.event_id for item in store.observations_for(game_id, actor_id)}
    actor_events.update(
        item.entry_id for item in store.agent_context_entries(game_id, actor_id)
        if item.channel == "npc_spoke"
    )
    memories: list[str] = []
    seen: set[str] = set()
    for item in reversed(store.observations_for(game_id, "player")):
        if item.event_id not in actor_events or item.event_id in seen:
            continue
        seen.add(item.event_id)
        if len(memories) >= limit:
            continue
        content = item.content.strip()
        if item.channel == "dialogue" and content.startswith("【") and "】\n" in content:
            content = content.split("】\n", 1)[1].strip()
        content = " ".join(content.split())
        if content:
            memories.append(content[:177].rstrip() + "…" if len(content) > 180 else content)
    return len(seen), memories
