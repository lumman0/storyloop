from __future__ import annotations

from copy import deepcopy

from storyloop_harness.core.contracts import Snapshot, WorldEvent


def apply_event(snapshot: Snapshot, event: WorldEvent) -> Snapshot:
    """Return the state after one committed event, leaving input untouched."""
    if event.tick < snapshot.tick:
        raise ValueError("event tick precedes the current world tick")

    data = deepcopy(snapshot.data)
    for effect in event.effects:
        if not effect.path:
            raise ValueError("effect path cannot be empty")
        node = data
        for segment in effect.path[:-1]:
            if not isinstance(node, dict) or segment not in node:
                raise ValueError(f"unknown effect path: {effect.path!r}")
            node = node[segment]
        leaf = effect.path[-1]
        if not isinstance(node, dict) or leaf not in node:
            raise ValueError(f"unknown effect path: {effect.path!r}")
        node[leaf] = deepcopy(effect.value)

    return Snapshot(
        game_id=snapshot.game_id,
        version=snapshot.version + 1,
        tick=event.tick,
        data=data,
    )
