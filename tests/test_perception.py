import tempfile
import unittest
from pathlib import Path

from storyloop_harness.core.contracts import Effect, PendingWork, Snapshot, WorldEvent
from storyloop_harness.runtime.runner import TurnRunner, WorkResult
from storyloop_platform.adapters.store import SQLiteGameStore


class PerceptionTests(unittest.TestCase):
    def test_committed_physical_change_reaches_only_colocated_observers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            store.create_game(
                Snapshot("game", 0, 0, {
                    "world": {"window": {"broken": False}},
                    "actors": {
                        "player": {"location": "hall"},
                        "A": {"location": "hall"},
                        "B": {"location": "garden"},
                        "C": {"location": "tower"},
                    },
                }),
                (PendingWork("break", "break_window", 0, 1, None, {}),),
            )

            def break_window(snapshot: Snapshot, work: PendingWork) -> WorkResult:
                event = WorldEvent(
                    "window-broken", "window_broken", "player", work.work_id, 1,
                    (Effect(("world", "window", "broken"), True),),
                    details={"location": "hall", "sensory": "玩家打破了大厅的窗户"},
                )
                return WorkResult(event, (), ())

            TurnRunner(store, {"break_window": break_window}, 2).run("game")

            self.assertEqual([item.content for item in store.observations_for("game", "A")], ["玩家打破了大厅的窗户"])
            self.assertEqual([item.content for item in store.observations_for("game", "player")], ["玩家打破了大厅的窗户"])
            self.assertEqual(store.observations_for("game", "B"), [])
            self.assertEqual(store.observations_for("game", "C"), [])


if __name__ == "__main__":
    unittest.main()
