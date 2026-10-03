"""Script-declared, save-authoritative status fields and player projection."""

from __future__ import annotations

from dataclasses import dataclass

from story_harness.core.contracts import Effect, Snapshot


def _value_at(state: dict[str, object], path: tuple[str, ...]) -> object:
    value: object = state
    for segment in path:
        if not isinstance(value, dict) or segment not in value:
            raise ValueError(f"unknown status path: {'.'.join(path)}")
        value = value[segment]
    return value


def _path(raw: object) -> tuple[str, ...]:
    if (not isinstance(raw, list) or not raw
            or any(not isinstance(part, str) or not part for part in raw)):
        raise ValueError("status path must be a nonempty list of keys")
    path = tuple(raw)
    if path[0] == "scenario":
        raise ValueError("scenario metadata cannot be a status path")
    return path


@dataclass(frozen=True)
class StatusField:
    field_id: str
    label: str
    path: tuple[str, ...]
    visible: bool = True
    description: str = ""
    minimum: int | None = None
    maximum: int | None = None
    max_delta: int | None = None
    when_path: tuple[str, ...] | None = None
    when_equals: object = None

    @property
    def automatically_updated(self) -> bool:
        return self.max_delta is not None


def parse_status_fields(raw: object, initial_state: dict[str, object]) -> tuple[StatusField, ...]:
    if not isinstance(raw, list):
        raise ValueError("status_fields must be a list")
    fields: list[StatusField] = []
    seen_ids: set[str] = set()
    seen_paths: set[tuple[str, ...]] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("status field must be an object")
        field_id, label = item.get("id"), item.get("label")
        if (not isinstance(field_id, str) or not field_id.strip()
                or not isinstance(label, str) or not label.strip()):
            raise ValueError("status field requires id and label")
        field_id = field_id.strip()
        path = _path(item.get("path"))
        value = _value_at(initial_state, path)
        if type(value) not in {str, bool, int}:
            raise ValueError("status field must point to a scalar value")
        if field_id in seen_ids or path in seen_paths:
            raise ValueError("duplicate status field id or path")
        visible = item.get("visible", True)
        description = item.get("description", "")
        if type(visible) is not bool or not isinstance(description, str):
            raise ValueError("status visibility and description must have valid types")
        bounds = item.get("bounds")
        minimum = maximum = max_delta = None
        if bounds is not None:
            if not isinstance(bounds, dict) or type(value) is not int:
                raise ValueError("status bounds require an integer state field")
            minimum, maximum, max_delta = (bounds.get(key) for key in ("min", "max", "max_delta"))
            if (any(type(part) is not int for part in (minimum, maximum, max_delta))
                    or minimum >= maximum or max_delta < 1
                    or not minimum <= value <= maximum):
                raise ValueError("invalid status bounds")
        when = item.get("when")
        when_path = None
        when_equals = None
        if when is not None:
            if not isinstance(when, dict) or "equals" not in when:
                raise ValueError("status when must have path and equals")
            when_path = _path(when.get("path"))
            observed = _value_at(initial_state, when_path)
            when_equals = when["equals"]
            if type(when_equals) is not type(observed):
                raise ValueError("status when value must match state type")
        fields.append(StatusField(field_id, label.strip(), path, visible,
                                  description, minimum, maximum, max_delta,
                                  when_path, when_equals))
        seen_ids.add(field_id)
        seen_paths.add(path)
    return tuple(fields)


def project_status_fields(fields: tuple[StatusField, ...],
                          state: dict[str, object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for field in fields:
        if not field.visible:
            continue
        try:
            if (field.when_path is not None
                    and _value_at(state, field.when_path) != field.when_equals):
                continue
            value = _value_at(state, field.path)
        except ValueError:
            # A package may support both campaign and freeform saves. The
            # latter intentionally omits its campaign-only state subtree.
            continue
        item: dict[str, object] = {"id": field.field_id, "label": field.label,
                                   "value": value}
        if field.minimum is not None:
            item["min"] = field.minimum
            item["max"] = field.maximum
        result.append(item)
    return result


def status_effects(fields: tuple[StatusField, ...], snapshot: Snapshot,
                   changes: list[dict[str, object]]) -> tuple[Effect, ...]:
    allowed = {field.field_id: field for field in fields if field.automatically_updated}
    seen: set[str] = set()
    effects: list[Effect] = []
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError("status change must be an object")
        field_id, delta = change.get("id"), change.get("delta")
        if not isinstance(field_id, str) or field_id not in allowed:
            raise ValueError("unknown automatically updated status field")
        if field_id in seen:
            raise ValueError("duplicate status change")
        seen.add(field_id)
        field = allowed[field_id]
        if type(delta) is not int or not -field.max_delta <= delta <= field.max_delta:
            raise ValueError("status delta exceeds configured limit")
        current = _value_at(snapshot.data, field.path)
        if type(current) is not int:
            raise ValueError("status field changed type in the save")
        value = max(field.minimum, min(field.maximum, current + delta))
        if value != current:
            effects.append(Effect(field.path, value))
    return tuple(effects)
