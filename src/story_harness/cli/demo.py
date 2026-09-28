"""Deterministic causal-flow demonstration without a language model."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from story_harness.core.contracts import Effect, Observation, PendingWork, Snapshot, WorldEvent
from story_harness.runtime.runner import TurnRunner, WorkResult
from story_harness.adapters.store import SQLiteGameStore


def break_window(snapshot: Snapshot, work: PendingWork) -> WorkResult:
    event = WorldEvent(
        "window-broken",
        "window_broken",
        "player",
        work.work_id,
        snapshot.tick + 1,
        (Effect(("world", "window", "broken"), True),),
        details={"location": "hall", "sensory": "亲眼看到玩家打破窗户"},
    )
    actor_a = snapshot.data["actors"]["A"]
    can_tell = actor_a["location"] == "hall" and actor_a["friend_id"] == "B"
    followup = (PendingWork("tell", "tell_b", event.tick, 5, event.event_id, {}),) if can_tell else ()
    return WorkResult(event, (), followup)


def tell_b(snapshot: Snapshot, work: PendingWork, store: SQLiteGameStore) -> WorkResult:
    if not any(item.event_id == work.cause_id for item in store.observations_for(snapshot.game_id, "A")):
        return WorkResult(None, (), ())
    event = WorldEvent(
        "a-told-b",
        "rumor_shared",
        "A",
        work.cause_id,
        snapshot.tick,
        (),
    )
    hearsay = Observation(
        "b-heard-window",
        event.event_id,
        "B",
        "told",
        "A 告诉我玩家打破了窗户",
        event.tick,
    )
    return WorkResult(event, (hearsay,), ())


def run_demo(a_present: bool = True) -> dict[str, object]:
    with TemporaryDirectory() as directory:
        store = SQLiteGameStore(str(Path(directory) / "demo.sqlite3"))
        store.create_game(
            Snapshot("demo", 0, 0, {
                "world": {"window": {"broken": False}},
                "actors": {
                    "player": {"location": "hall"},
                    "A": {"location": "hall" if a_present else "tower", "friend_id": "B"},
                    "B": {"location": "garden"},
                    "C": {"location": "tower"},
                },
            }),
            (PendingWork("break", "break_window", 0, 10, None, {}),),
        )
        result = TurnRunner(
            store,
            {"break_window": break_window, "tell_b": lambda snapshot, work: tell_b(snapshot, work, store)},
            max_steps=10,
        ).run("demo")
        return {
            "window_broken": result.snapshot.data["world"]["window"]["broken"],
            "A": [item.content for item in store.observations_for("demo", "A")],
            "B": [item.content for item in store.observations_for("demo", "B")],
            "C": [item.content for item in store.observations_for("demo", "C")],
            "player": [item.content for item in store.observations_for("demo", "player")],
            "processed": list(result.processed_work_ids),
        }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
