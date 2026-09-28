"""Declarative action rules; the model selects IDs but cannot author effects."""

from __future__ import annotations

from dataclasses import dataclass

from story_harness.core.contracts import Effect, Observation, Snapshot, WorldEvent


def _path(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw or not all(isinstance(x, str) and x for x in raw):
        raise ValueError("action path must be a nonempty list of keys")
    return tuple(raw)


def _read(data: dict[str, object], path: tuple[str, ...]) -> object:
    node: object = data
    for segment in path:
        if not isinstance(node, dict) or segment not in node:
            raise ValueError(f"unknown action state path: {path!r}")
        node = node[segment]
    return node


@dataclass(frozen=True)
class ActionRule:
    action_id: str
    label: str
    location: str
    when_path: tuple[str, ...]
    when_value: object
    effects: tuple[Effect, ...]
    sensory: str


def parse_action_rules(raw: object, initial_state: dict[str, object]) -> dict[str, ActionRule]:
    if not isinstance(raw, list):
        raise ValueError("actions must be a list")
    rules: dict[str, ActionRule] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("action declaration must be an object")
        action_id = item.get("id")
        label = item.get("label")
        location = item.get("location")
        sensory = item.get("sensory")
        if not all(isinstance(x, str) and x for x in (action_id, label, location, sensory)):
            raise ValueError("action requires id, label, location and sensory")
        if action_id in rules:
            raise ValueError("duplicate action ID")
        when = item.get("when")
        if not isinstance(when, dict) or "value" not in when:
            raise ValueError(f"action {action_id} requires when condition")
        when_path = _path(when.get("path"))
        _read(initial_state, when_path)
        raw_effects = item.get("effects")
        if not isinstance(raw_effects, list) or not raw_effects:
            raise ValueError(f"action {action_id} requires effects")
        effects: list[Effect] = []
        for declaration in raw_effects:
            if not isinstance(declaration, dict) or "value" not in declaration:
                raise ValueError(f"invalid effect for action {action_id}")
            path = _path(declaration.get("path"))
            _read(initial_state, path)
            effects.append(Effect(path, declaration["value"]))
        rules[action_id] = ActionRule(
            action_id, label, location, when_path, when["value"], tuple(effects), sensory
        )
    return rules


def adjudicate_action(
    before: Snapshot, rule: ActionRule, event_id: str, player_text: str
) -> tuple[WorldEvent, tuple[Observation, ...]]:
    """Adjudicate against current state; a rejected attempt still becomes history."""
    actors = before.data.get("actors", {})
    player = actors.get("player", {}) if isinstance(actors, dict) else {}
    location = player.get("location") if isinstance(player, dict) else None
    reason: str | None = None
    if location != rule.location:
        reason = "你当前不在这个行动所需的位置。"
    elif _read(before.data, rule.when_path) != rule.when_value:
        reason = "当前状态已不允许重复完成这个行动。"
    tick = before.tick + 1
    if reason is not None:
        event = WorldEvent(
            event_id, "action_rejected", "player", None, tick, (),
            details={"action_id": rule.action_id, "text": player_text, "reason": reason},
        )
        observation = Observation(
            f"{event_id}:player-result", event_id, "player", "action_result", reason, tick
        )
        return event, (observation,)
    event = WorldEvent(
        event_id, "player_action", "player", None, tick, rule.effects,
        details={
            "action_id": rule.action_id, "text": player_text,
            "location": rule.location, "sensory": rule.sensory,
        },
    )
    return event, ()
