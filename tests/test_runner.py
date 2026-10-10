import tempfile
import unittest
from pathlib import Path

from storyloop_harness.advanced import Effect, Observation, PendingWork, Snapshot, WorldEvent
from storyloop_harness.advanced import TurnRunner, WorkResult
from storyloop_platform.adapters.store import SQLiteGameStore


class DynamicRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = str(Path(self.temp.name) / "runner.sqlite3")
        self.store = SQLiteGameStore(self.db_path)
        self.store.create_game(
            Snapshot("game-1", 0, 0, {"world": {"window": {"broken": False}}}),
            (PendingWork("break", "break_window", 0, 10, None, {}),),
        )

    @staticmethod
    def break_window(snapshot: Snapshot, work: PendingWork) -> WorkResult:
        event = WorldEvent(
            "break-event",
            "window_broken",
            "player",
            work.work_id,
            1,
            (Effect(("world", "window", "broken"), True),),
        )
        observed = Observation("obs-a", event.event_id, "A", "witnessed", "窗户碎了", 1)
        followup = PendingWork("tell", "tell_b", 1, 5, event.event_id, {})
        return WorkResult(event, (observed,), (followup,))

    @staticmethod
    def tell_b(snapshot: Snapshot, work: PendingWork) -> WorkResult:
        event = WorldEvent("tell-event", "rumor_shared", "A", work.cause_id, 1, ())
        observed = Observation("obs-b", event.event_id, "B", "told", "A 说窗户碎了", 1)
        return WorkResult(event, (observed,), ())


    def test_new_runner_resumes_without_repeating_the_first_event(self) -> None:
        handlers = {"break_window": self.break_window, "tell_b": self.tell_b}
        TurnRunner(self.store, handlers, max_steps=1).run("game-1")
        restarted = TurnRunner(SQLiteGameStore(self.db_path), handlers, max_steps=1)

        result = restarted.run("game-1")

        self.assertEqual(result.processed_work_ids, ("tell",))
        self.assertEqual(result.snapshot.version, 2)
        self.assertEqual(len(self.store.observations_for("game-1", "A")), 1)
        self.assertEqual(len(self.store.observations_for("game-1", "B")), 1)


if __name__ == "__main__":
    unittest.main()
