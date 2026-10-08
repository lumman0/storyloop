"""Open player actions and the narrow state fields they may change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from storyloop_harness.core.contracts import Effect


def _read_path(state: dict[str, object], path: tuple[str, ...]) -> object:
    value: object = state
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"unknown mutable state path: {'.'.join(path)}")
        value = value[key]
    return value


@dataclass(frozen=True)
class MutableField:
    path: tuple[str, ...]
    values: tuple[object, ...]
    transitions: tuple[tuple[object, tuple[object, ...]], ...] = ()

    def next_values(self, current: object) -> tuple[object, ...]:
        if not self.transitions:
            return self.values
        return next((choices for source, choices in self.transitions if source == current), ())


def parse_mutable_fields(raw: object, initial_state: dict[str, object]) -> tuple[MutableField, ...]:
    """Declare state fields, not player verbs; effects still require runtime validation."""
    if not isinstance(raw, list):
        raise ValueError("mutable_state must be a list")
    fields: list[MutableField] = []
    seen: set[tuple[str, ...]] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("mutable state field must be an object")
        raw_path, raw_values = item.get("path"), item.get("values")
        if (not isinstance(raw_path, list) or not raw_path
                or not all(isinstance(key, str) and key for key in raw_path)):
            raise ValueError("mutable state path must be a nonempty list of keys")
        path = tuple(raw_path)
        if path in seen or path[0] in {"scenario", "campaign"}:
            raise ValueError("duplicate or reserved mutable state path")
        current = _read_path(initial_state, path)
        if type(current) not in {str, bool, int}:
            raise ValueError("mutable state field must have a scalar initial value")
        if (not isinstance(raw_values, list) or not raw_values
                or any(type(value) is not type(current) for value in raw_values)
                or current not in raw_values):
            raise ValueError("mutable state values must include the current value and keep its type")
        raw_transitions = item.get("transitions", [])
        if not isinstance(raw_transitions, list):
            raise ValueError("mutable state transitions must be a list")
        transitions: list[tuple[object, tuple[object, ...]]] = []
        for transition in raw_transitions:
            if not isinstance(transition, dict) or set(transition) != {"from", "to"}:
                raise ValueError("mutable state transition requires from and to")
            source, targets = transition["from"], transition["to"]
            if (type(source) is not type(current) or source not in raw_values
                    or any(prior == source for prior, _ in transitions)
                    or not isinstance(targets, list) or not targets
                    or any(type(target) is not type(current) or target not in raw_values
                           or target == source for target in targets)
                    or len(targets) != len(set(targets))):
                raise ValueError("mutable state transition values must be declared and distinct")
            transitions.append((source, tuple(targets)))
        fields.append(MutableField(path, tuple(raw_values), tuple(transitions)))
        seen.add(path)
    return tuple(fields)


def validate_open_effects(effects: tuple[Effect, ...], fields: tuple[MutableField, ...],
                          current_state: dict[str, object]) -> None:
    allowed = {field.path: field for field in fields}
    seen: set[tuple[str, ...]] = set()
    for effect in effects:
        if effect.path in seen or effect.path not in allowed:
            raise ValueError("action proposed an undeclared or duplicate state effect")
        current = _read_path(current_state, effect.path)
        field = allowed[effect.path]
        if (type(effect.value) is not type(current)
                or effect.value not in field.next_values(current)):
            raise ValueError("action proposed a state value outside the declared field")
        seen.add(effect.path)


@dataclass(frozen=True)
class OpenActionOutcome:
    status: Literal["occurred", "attempted", "blocked"]
    player_result: str
    sensory: str
    target_ids: tuple[str, ...] = ()
    effects: tuple[Effect, ...] = ()

    def __post_init__(self) -> None:
        if (self.status not in {"occurred", "attempted", "blocked"}
                or not self.player_result.strip() or not self.sensory.strip()
                or len(set(self.target_ids)) != len(self.target_ids)
                or (self.status != "occurred" and self.effects)):
            raise ValueError("invalid open action resolution")
