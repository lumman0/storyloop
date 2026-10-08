"""Logical time and conditional background cues shared by scenarios."""

from __future__ import annotations

from story_harness.core.contracts import Effect, PendingWork, Snapshot, WorldEvent
from story_harness.runtime.runner import WorkResult
from story_harness.core.store_port import GameStore


def advance_time(store: GameStore, game_id: str, tick: int, event_id: str) -> Snapshot:
    """Advance a game's clock; callers choose how much time an action costs."""
    before = store.load(game_id)
    if type(tick) is not int or tick < before.tick:
        raise ValueError("time cannot move backward")
    if not event_id:
        raise ValueError("time advancement requires an event ID")
    event = WorldEvent(event_id, "time_advanced", None, None, tick, ())
    return store.commit(game_id, before.version, event, (), ())


def _path(raw: object, label: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw or not all(
        isinstance(segment, str) and segment for segment in raw
    ):
        raise ValueError(f"{label} must be a nonempty path")
    return tuple(raw)


def _read(data: dict[str, object], path: tuple[str, ...]) -> object:
    node: object = data
    for segment in path:
        if not isinstance(node, dict) or segment not in node:
            raise ValueError(f"unknown condition path: {path!r}")
        node = node[segment]
    return node


def _cue_effects(state: dict[str, object], payload: dict[str, object]) -> tuple[Effect, ...]:
    if "effects" in payload:
        if "effect_path" in payload or "effect_value" in payload:
            raise ValueError("cue must use either effects or effect_path")
        raw_effects = payload["effects"]
        if not isinstance(raw_effects, list) or not raw_effects:
            raise ValueError("scenario cue effects must be a nonempty list")
        declarations = raw_effects
    else:
        if "effect_value" not in payload:
            raise ValueError("scenario cue requires effect_value")
        declarations = [{"path": payload.get("effect_path"), "value": payload["effect_value"]}]
    effects: list[Effect] = []
    for declaration in declarations:
        if not isinstance(declaration, dict) or "value" not in declaration:
            raise ValueError("scenario cue effect requires path and value")
        path = _path(declaration.get("path"), "effect path")
        try:
            _read(state, path)
        except ValueError as error:
            raise ValueError(f"unknown effect path: {path!r}") from error
        effects.append(Effect(path, declaration["value"]))
    return tuple(effects)


def validate_scenario_cue(state: dict[str, object], payload: dict[str, object]) -> None:
    kind = payload.get("event_kind")
    summary = payload.get("summary")
    if not isinstance(kind, str) or not kind or not isinstance(summary, str):
        raise ValueError("scenario cue requires event_kind and summary")
    _cue_effects(state, payload)
    if "location" in payload or "sensory" in payload:
        if not isinstance(payload.get("location"), str) or not payload["location"]:
            raise ValueError("scenario cue announcement requires location")
        if not isinstance(payload.get("sensory"), str) or not payload["sensory"]:
            raise ValueError("scenario cue announcement requires sensory summary")
    if "when_path" in payload:
        condition_path = _path(payload["when_path"], "when_path")
        current = _read(state, condition_path)
        if ("when_value" in payload) == ("when_values" in payload):
            raise ValueError("scenario cue requires exactly one of when_value or when_values")
        if "when_values" in payload:
            values = payload["when_values"]
            if (not isinstance(values, list) or not values
                    or any(type(value) is not type(current) for value in values)):
                raise ValueError("scenario cue when_values must match the state field")


def scenario_cue(snapshot: Snapshot, work: PendingWork) -> WorkResult:
    """Recheck a declared condition when a schedule cue becomes due."""
    payload = work.payload
    validate_scenario_cue(snapshot.data, payload)
    kind = payload["event_kind"]
    summary = payload["summary"]
    effects = _cue_effects(snapshot.data, payload)
    if "when_path" in payload:
        condition_path = _path(payload["when_path"], "when_path")
        current = _read(snapshot.data, condition_path)
        accepted = (payload["when_values"] if "when_values" in payload
                    else [payload["when_value"]])
        if current not in accepted:
            return WorkResult(None, (), ())
    details: dict[str, object] = {"summary": summary, "scheduled_work_id": work.work_id}
    if "location" in payload:
        details["location"] = payload["location"]
        details["sensory"] = payload["sensory"]
    event = WorldEvent(
        event_id=f"{work.work_id}:occurred",
        kind=kind,
        actor_id=None,
        cause_id=work.cause_id,
        tick=snapshot.tick,
        effects=effects,
        details=details,
    )
    return WorkResult(event, (), ())
