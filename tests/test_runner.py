import asyncio
import tempfile
import unittest
from pathlib import Path

from storyloop_harness.core.contracts import Effect, Observation, PendingWork, Snapshot, WorldEvent
from storyloop_harness.runtime.runner import TurnRunner, WorkResult
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

    def test_work_can_enqueue_another_handler_dynamically(self) -> None:
        runner = TurnRunner(
            self.store,
            {"break_window": self.break_window, "tell_b": self.tell_b},
            max_steps=2,
        )

        result = runner.run("game-1")

        self.assertEqual(result.processed_work_ids, ("break", "tell"))
        self.assertEqual(result.remaining_work_ids, ())
        self.assertEqual(result.snapshot.version, 2)
        self.assertEqual(len(self.store.observations_for("game-1", "A")), 1)
        self.assertEqual(len(self.store.observations_for("game-1", "B")), 1)
        self.assertEqual(self.store.observations_for("game-1", "C"), [])

    def test_budget_preserves_followup_for_a_later_turn(self) -> None:
        result = TurnRunner(
            self.store,
            {"break_window": self.break_window, "tell_b": self.tell_b},
            max_steps=1,
        ).run("game-1")

        self.assertEqual(result.processed_work_ids, ("break",))
        self.assertEqual(result.remaining_work_ids, ("tell",))
        self.assertEqual(result.snapshot.version, 1)

    def test_observation_does_not_automatically_wake_an_npc(self) -> None:
        npc_calls: list[str] = []

        def npc_decide(snapshot: Snapshot, work: PendingWork) -> WorkResult:
            npc_calls.append(work.work_id)
            return WorkResult(None, (), ())

        runner = TurnRunner(
            self.store,
            {"break_window": self.break_window, "npc_decide": npc_decide},
            max_steps=1,
        )

        runner.run("game-1")

        self.assertEqual(npc_calls, [])
        self.assertEqual(len(self.store.observations_for("game-1", "A")), 1)

    def test_new_runner_resumes_without_repeating_the_first_event(self) -> None:
        handlers = {"break_window": self.break_window, "tell_b": self.tell_b}
        TurnRunner(self.store, handlers, max_steps=1).run("game-1")
        restarted = TurnRunner(SQLiteGameStore(self.db_path), handlers, max_steps=1)

        result = restarted.run("game-1")

        self.assertEqual(result.processed_work_ids, ("tell",))
        self.assertEqual(result.snapshot.version, 2)
        self.assertEqual(len(self.store.observations_for("game-1", "A")), 1)
        self.assertEqual(len(self.store.observations_for("game-1", "B")), 1)

    def test_async_handler_runs_through_the_same_queue(self) -> None:
        async def async_break(snapshot: Snapshot, work: PendingWork) -> WorkResult:
            await asyncio.sleep(0)
            return self.break_window(snapshot, work)

        runner = TurnRunner(self.store, {"break_window": async_break}, max_steps=1)

        result = asyncio.run(runner.run_async("game-1"))

        self.assertEqual(result.processed_work_ids, ("break",))
        self.assertEqual(result.snapshot.version, 1)

    def test_selector_can_choose_among_discretionary_work(self) -> None:
        self.store.commit(
            "game-1",
            0,
            None,
            (),
            (
                PendingWork("a", "noop", 0, 1, None, {}, mandatory=False),
                PendingWork("b", "noop", 0, 1, None, {}, mandatory=False),
            ),
            consumed_work_id="break",
        )
        selected: list[str] = []

        def choose(snapshot: Snapshot, options: list[PendingWork]) -> PendingWork:
            selected.append(",".join(item.work_id for item in options))
            return next(item for item in options if item.work_id == "b")

        runner = TurnRunner(
            self.store,
            {"noop": lambda snapshot, work: WorkResult(None, (), ())},
            max_steps=1,
            selector=choose,
        )

        result = runner.run("game-1")

        self.assertEqual(result.processed_work_ids, ("b",))
        self.assertEqual(result.remaining_work_ids, ("a",))
        self.assertEqual(selected, ["a,b"])

    def test_mandatory_work_precedes_discretionary_selection(self) -> None:
        self.store.commit(
            "game-1",
            0,
            None,
            (),
            (PendingWork("optional", "noop", 0, 99, None, {}, mandatory=False),),
        )

        def selector(snapshot: Snapshot, options: list[PendingWork]) -> PendingWork:
            raise AssertionError("selector must not bypass mandatory work")

        runner = TurnRunner(
            self.store,
            {"break_window": self.break_window, "noop": lambda s, w: WorkResult(None, (), ())},
            max_steps=1,
            selector=selector,
        )

        self.assertEqual(runner.run("game-1").processed_work_ids, ("break",))


if __name__ == "__main__":
    unittest.main()
