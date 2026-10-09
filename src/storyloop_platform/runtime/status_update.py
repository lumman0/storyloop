"""Apply bounded status changes as committed events after a story turn."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from storyloop_platform.adapters.store import GameStore
from storyloop_harness.advanced import Observation, Snapshot, WorldEvent
from storyloop_harness.advanced import StatusField, value_at as _value_at, status_effects


StatusProposer = Callable[
    [Snapshot, str, tuple[str, ...], tuple[StatusField, ...]],
    Awaitable[list[dict[str, object]]],
]


async def settle_status(store: GameStore, game_id: str, turn_id: str,
                        player_text: str, fields: tuple[StatusField, ...],
                        observations: tuple[Observation, ...],
                        propose: StatusProposer) -> Snapshot:
    """Review player-visible events once; NPC-private facts never enter this decision."""
    snapshot = store.load(game_id)
    updatable: tuple[StatusField, ...] = tuple(
        field for field in fields
        if field.automatically_updated and _present(snapshot.data, field.path)
    )
    event_id = f"{turn_id}:status"
    if not updatable or store.event_exists(game_id, event_id):
        return snapshot
    evidence = tuple(item.content[:1200] for item in observations
                     if item.recipient_id == "player")[-16:]
    if not evidence:
        return snapshot
    changes = await propose(snapshot, player_text, evidence, updatable)
    effects = status_effects(updatable, snapshot, changes)
    event = WorldEvent(event_id, "status_review", None, turn_id, snapshot.tick, effects,
                       {"changes": changes,
                        "evidence_ids": [item.observation_id for item in observations
                                         if item.recipient_id == "player"]})
    return store.commit(game_id, snapshot.version, event, (), ())


def _present(state: dict[str, object], path: tuple[str, ...]) -> bool:
    try:
        _value_at(state, path)
        return True
    except ValueError:
        return False
