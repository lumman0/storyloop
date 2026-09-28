import tempfile
import unittest
from pathlib import Path

from story_harness.core.contracts import Effect, PendingWork, Snapshot, WorldEvent
from story_harness.runtime.runner import TurnRunner, WorkResult
from story_harness.adapters.store import SQLiteGameStore
from story_harness.adapters.telemetry import LangfuseTelemetry


class FakeSpan:
    def __init__(self, sink: list[tuple[str, object]]) -> None:
        self.sink = sink

    def update(self, **kwargs: object) -> None:
        self.sink.append(("update", kwargs))


class FakeContext:
    def __init__(self, sink: list[tuple[str, object]]) -> None:
        self.sink = sink

    def __enter__(self) -> FakeSpan:
        return FakeSpan(self.sink)

    def __exit__(self, *args: object) -> None:
        return None


class FakeLangfuse:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def start_as_current_observation(self, **kwargs: object) -> FakeContext:
        self.calls.append(("start", kwargs))
        return FakeContext(self.calls)


class TelemetryTests(unittest.TestCase):
    def test_runner_emits_turn_work_and_event_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            store.create_game(Snapshot("game", 0, 0, {"world": {"window": {"broken": False}}}), (PendingWork("w1", "step", 0, 1, None, {}),))
            client = FakeLangfuse()
            runner = TurnRunner(
                store,
                {"step": lambda snapshot, work: WorkResult(WorldEvent("e1", "happened", None, work.work_id, 0, (Effect(("world", "window", "broken"), True),)), (), ())},
                1,
                telemetry=LangfuseTelemetry(client),
            )

            runner.run("game")

            starts = [value for kind, value in client.calls if kind == "start"]
            self.assertEqual([item["name"] for item in starts], ["game-turn", "work:step"])
            self.assertEqual(starts[0]["metadata"]["game_id"], "game")
            self.assertEqual(starts[1]["metadata"]["work_id"], "w1")
            self.assertTrue(any(value.get("metadata", {}).get("event_id") == "e1" for kind, value in client.calls if kind == "update"))
            self.assertTrue(any(
                value.get("metadata", {}).get("effect_paths") == ["world.window.broken"]
                for kind, value in client.calls if kind == "update"
            ))

    def test_observability_failure_does_not_block_world_commit(self) -> None:
        class BrokenLangfuse:
            def start_as_current_observation(self, **kwargs: object) -> FakeContext:
                raise RuntimeError("telemetry unavailable")

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            store.create_game(Snapshot("game", 0, 0, {}), (PendingWork("w1", "step", 0, 1, None, {}),))
            runner = TurnRunner(
                store,
                {"step": lambda snapshot, work: WorkResult(WorldEvent("e1", "happened", None, work.work_id, 0, ()), (), ())},
                1,
                telemetry=LangfuseTelemetry(BrokenLangfuse()),
            )

            result = runner.run("game")

            self.assertEqual(result.snapshot.version, 1)
            self.assertEqual(result.processed_work_ids, ("w1",))


if __name__ == "__main__":
    unittest.main()
