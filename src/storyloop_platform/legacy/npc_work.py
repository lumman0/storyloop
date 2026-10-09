"""Bridge queued NPC decisions to AgentScope agents and event storage."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from storyloop_platform.legacy.npc_agent import NpcAgentPool
from storyloop_harness.advanced import Observation, PendingWork, Snapshot, WorldEvent
from storyloop_harness.advanced import WorkHandler, WorkResult


def make_npc_reply_handler(
    pool: NpcAgentPool, role_cards: Mapping[str, str], display_names: Mapping[str, str] | None = None,
) -> WorkHandler:
    names = display_names or {}
    label_counts = Counter(names.get(actor_id, actor_id) for actor_id in role_cards)

    async def handle(snapshot: Snapshot, work: PendingWork) -> WorkResult:
        actor_id = work.payload.get("actor_id")
        player_message = work.payload.get("player_message")
        duration_ticks = work.payload.get("duration_ticks", 1)
        if not isinstance(actor_id, str) or not isinstance(player_message, str):
            raise ValueError("NPC reply work requires actor_id and player_message")
        if type(duration_ticks) is not int or duration_ticks < 0:
            raise ValueError("duration_ticks must be a nonnegative integer")
        if "campaign" in snapshot.data and duration_ticks > 0:
            raise ValueError("campaign NPC reply duration_ticks must be zero")
        if actor_id not in role_cards:
            raise ValueError(f"unknown NPC: {actor_id}")

        prepared = await pool.prepare_response(
            snapshot.game_id,
            actor_id,
            role_cards[actor_id],
            player_message,
            current_input_event_id=work.cause_id,
        )
        label = names.get(actor_id, actor_id)
        if label_counts[label] > 1:
            label = f"{label} ({actor_id})"
        event = WorldEvent(
            event_id=f"{work.work_id}:spoken",
            kind="npc_spoke",
            actor_id=actor_id,
            cause_id=work.cause_id,
            tick=snapshot.tick + duration_ticks,
            effects=(),
            details={"player_message": player_message, "speech": prepared.speech,
                     "speaker_id": actor_id, "speaker_name": label},
        )
        player_heard = Observation(
            observation_id=f"{work.work_id}:player-heard",
            event_id=event.event_id,
            recipient_id="player",
            channel="dialogue",
            content=f"【{label}】\n{prepared.speech.strip()}",
            tick=event.tick,
        )
        return WorkResult(
            event,
            (player_heard,),
            (),
            on_commit=prepared.confirm,
            on_abort=prepared.abort,
        )

    return handle
