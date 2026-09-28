"""Produce observer-scoped facts from a committed physical event candidate."""

from __future__ import annotations

from story_harness.core.contracts import Observation, Snapshot, WorldEvent


def physical_observations(before: Snapshot, event: WorldEvent) -> tuple[Observation, ...]:
    """Witnesses are determined from positions before the event takes effect."""
    location = event.details.get("location")
    sensory = event.details.get("sensory")
    if location is None and sensory is None:
        return ()
    if not isinstance(location, str) or not location:
        raise ValueError("perceptible event requires a location")
    if not isinstance(sensory, str) or not sensory:
        raise ValueError("perceptible event requires a sensory summary")
    actors = before.data.get("actors", {})
    if not isinstance(actors, dict):
        raise ValueError("actors state must be an object")
    observations: list[Observation] = []
    for actor_id, state in actors.items():
        if isinstance(state, dict) and state.get("location") == location:
            observations.append(
                Observation(
                    observation_id=f"{event.event_id}:seen:{actor_id}",
                    event_id=event.event_id,
                    recipient_id=actor_id,
                    channel="witnessed",
                    content=sensory,
                    tick=event.tick,
                )
            )
    return tuple(observations)
