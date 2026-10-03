"""Load a small, versioned scenario package without executing source prose."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from story_harness.core.contracts import PendingWork, Snapshot
from story_harness.core.actions import ActionRule, parse_action_rules
from story_harness.core.open_actions import MutableField, parse_mutable_fields
from story_harness.runtime.schedule import validate_scenario_cue
from story_harness.adapters.store import GameStore
from story_harness.world.worldbook import Worldbook


def _required_string(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"scenario requires {key}")
    return value


@dataclass(frozen=True)
class ScenarioPackage:
    package_id: str
    version: str
    time_unit: str
    ticks_per_day: int | None
    actor_cards: tuple[tuple[str, str], ...]
    actor_names: dict[str, str]
    initial_state: dict[str, object]
    initial_work: tuple[PendingWork, ...]
    worldbook: Worldbook
    action_rules: dict[str, ActionRule]
    opening: str
    mutable_fields: tuple[MutableField, ...] = ()
    presentation_mode: str = "interactive"

    @property
    def role_cards(self) -> dict[str, str]:
        return {
            actor_id: self.worldbook.get(card_id, actor_id).text
            for actor_id, card_id in self.actor_cards
        }

    @classmethod
    def load(cls, directory: str | Path) -> ScenarioPackage:
        root = Path(directory).resolve()
        raw = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("scenario manifest must be an object")
        package_id = _required_string(raw, "id")
        version = _required_string(raw, "version")
        time_unit = _required_string(raw, "time_unit")
        opening = raw.get("opening", "")
        presentation_mode = raw.get("presentation_mode", "interactive")
        if not isinstance(presentation_mode, str) or presentation_mode not in {"interactive", "novel"}:
            raise ValueError("presentation_mode must be interactive or novel")
        if not isinstance(opening, str) or ("opening" in raw and not opening.strip()):
            raise ValueError("opening must be nonempty text when provided")
        if time_unit not in {"tick", "slot", "hour", "day", "week", "month"}:
            raise ValueError(f"unsupported time unit: {time_unit}")
        ticks_per_day = raw.get("ticks_per_day")
        if time_unit == "slot":
            if type(ticks_per_day) is not int or ticks_per_day < 1:
                raise ValueError("slot time requires positive ticks_per_day")
        elif ticks_per_day is not None:
            raise ValueError("ticks_per_day is only valid for slot time")

        book_path = (root / _required_string(raw, "worldbook")).resolve()
        if not book_path.is_relative_to(root) or book_path == root:
            raise ValueError("worldbook must stay inside the package")
        worldbook = Worldbook.load(book_path)
        if (worldbook.package_id, worldbook.version) != (package_id, version):
            raise ValueError("worldbook identity does not match the scenario")

        raw_actors = raw.get("actors")
        if not isinstance(raw_actors, list):
            raise ValueError("actors must be a list")
        actors: list[tuple[str, str]] = []
        actor_names: dict[str, str] = {}
        for item in raw_actors:
            if not isinstance(item, dict):
                raise ValueError("actor declaration must be an object")
            actor_id = _required_string(item, "id")
            card_id = _required_string(item, "card")
            name = item.get("name", actor_id)
            if not isinstance(name, str) or not name.strip() or "\n" in name or "\r" in name:
                raise ValueError("actor name must be a single nonempty line")
            if worldbook.get(card_id, actor_id) is None:
                raise ValueError(f"actor {actor_id} cannot read card {card_id}")
            actors.append((actor_id, card_id))
            actor_names[actor_id] = name.strip()
        if len({actor_id for actor_id, _ in actors}) != len(actors):
            raise ValueError("duplicate actor ID")

        state = raw.get("initial_state")
        if not isinstance(state, dict) or "scenario" in state:
            raise ValueError("initial_state must be an object without reserved scenario key")
        raw_work = raw.get("initial_work")
        if not isinstance(raw_work, list):
            raise ValueError("initial_work must be a list")
        work: list[PendingWork] = []
        for item in raw_work:
            if not isinstance(item, dict):
                raise ValueError("work declaration must be an object")
            work_id = _required_string(item, "id")
            kind = _required_string(item, "kind")
            due_tick = item.get("due_tick")
            priority = item.get("priority")
            payload = item.get("payload")
            mandatory = item.get("mandatory", True)
            if type(due_tick) is not int or due_tick < 0:
                raise ValueError(f"invalid due_tick for {work_id}")
            if type(priority) is not int:
                raise ValueError(f"invalid priority for {work_id}")
            if not isinstance(payload, dict) or type(mandatory) is not bool:
                raise ValueError(f"invalid payload or mandatory flag for {work_id}")
            if kind == "scenario_cue":
                validate_scenario_cue(state, payload)
            work.append(PendingWork(work_id, kind, due_tick, priority, None, payload, mandatory))
        if len({item.work_id for item in work}) != len(work):
            raise ValueError("duplicate work ID")

        action_rules = parse_action_rules(raw.get("actions", []), state)
        mutable_fields = parse_mutable_fields(raw.get("mutable_state", []), state)
        return cls(package_id, version, time_unit, ticks_per_day, tuple(actors), actor_names,
                   state, tuple(work), worldbook, action_rules, opening, mutable_fields,
                   presentation_mode)

    def seed_game(self, store: GameStore, game_id: str) -> None:
        state = deepcopy(self.initial_state)
        state["scenario"] = {
            "id": self.package_id,
            "version": self.version,
            "time_unit": self.time_unit,
            "ticks_per_day": self.ticks_per_day,
            "presentation_mode": self.presentation_mode,
        }
        store.create_game(Snapshot(game_id, 0, 0, state), self.initial_work)
