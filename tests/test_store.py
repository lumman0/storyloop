import tempfile
import unittest
from pathlib import Path

from story_harness.core.contracts import Effect, Observation, PendingWork, Snapshot, WorldEvent
from story_harness.adapters.store import SQLiteGameStore


def initial(game_id: str = "game-1") -> Snapshot:
    return Snapshot(game_id, 0, 0, {"world": {"window": {"broken": False}}})


def broken_event(event_id: str = "break-1") -> WorldEvent:
    return WorldEvent(
        event_id,
        "window_broken",
        "player",
        None,
        1,
        (Effect(("world", "window", "broken"), True),),
    )


class SQLiteGameStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = str(Path(self.temp.name) / "game.sqlite3")
        self.store = SQLiteGameStore(self.db_path)
        self.store.create_game(initial())

    def test_commit_writes_state_observation_and_followup_work_together(self) -> None:
        observation = Observation("obs-a", "break-1", "A", "witnessed", "窗户碎了", 1)
        work = PendingWork("tell-b", "tell", 1, 3, "break-1", {"recipient": "B"})

        updated = self.store.commit("game-1", 0, broken_event(), (observation,), (work,))

        self.assertEqual(updated.version, 1)
        self.assertTrue(self.store.load("game-1").data["world"]["window"]["broken"])
        self.assertEqual(self.store.observations_for("game-1", "A"), [observation])
        self.assertEqual(self.store.ready_work("game-1", 1), [work])

    def test_wrong_version_rolls_back_all_writes(self) -> None:
        observation = Observation("obs-a", "break-1", "A", "witnessed", "窗户碎了", 1)
        work = PendingWork("tell-b", "tell", 1, 3, "break-1", {"recipient": "B"})

        with self.assertRaises(ValueError):
            self.store.commit("game-1", 7, broken_event(), (observation,), (work,))

        self.assertEqual(self.store.load("game-1"), initial())
        self.assertEqual(self.store.observations_for("game-1", "A"), [])
        self.assertEqual(self.store.pending_work("game-1"), [])
        self.assertEqual(self.store.commit("game-1", 0, broken_event(), (), ()).version, 1)

    def test_duplicate_event_id_is_rejected_without_state_change(self) -> None:
        self.store.commit("game-1", 0, broken_event(), (), ())
        duplicate = WorldEvent("break-1", "window_broken", "player", None, 1, ())

        with self.assertRaises(ValueError):
            self.store.commit("game-1", 1, duplicate, (), ())

        self.assertEqual(self.store.load("game-1").version, 1)

    def test_same_event_id_is_isolated_by_game(self) -> None:
        self.store.create_game(initial("game-2"))
        self.store.commit("game-1", 0, broken_event(), (), ())
        self.store.commit("game-2", 0, broken_event(), (), ())

        self.assertTrue(self.store.load("game-1").data["world"]["window"]["broken"])
        self.assertTrue(self.store.load("game-2").data["world"]["window"]["broken"])

    def test_pending_work_survives_restart_and_can_be_consumed_without_event(self) -> None:
        work = PendingWork("player-act", "action", 0, 10, None, {})
        self.store.commit("game-1", 0, None, (), (work,))

        restarted = SQLiteGameStore(self.db_path)
        self.assertEqual(restarted.ready_work("game-1", 0), [work])
        after = restarted.commit("game-1", 0, None, (), (), consumed_work_id="player-act")

        self.assertEqual(after.version, 0)
        self.assertEqual(restarted.pending_work("game-1"), [])

    def test_consumed_work_id_cannot_be_enqueued_again(self) -> None:
        work = PendingWork("once", "award", 0, 1, None, {})
        self.store.commit("game-1", 0, None, (), (work,))
        self.store.commit("game-1", 0, None, (), (), consumed_work_id="once")

        with self.assertRaises(ValueError):
            self.store.commit("game-1", 0, None, (), (work,))

        self.assertEqual(self.store.pending_work("game-1"), [])

    def test_dialogue_history_is_persisted_for_its_actor_only(self) -> None:
        event = WorldEvent(
            "speech-1",
            "npc_spoke",
            "A",
            None,
            0,
            (),
            details={"player_message": "你好", "speech": "我看到了窗户"},
        )
        self.store.commit("game-1", 0, event, (), ())

        restarted = SQLiteGameStore(self.db_path)
        self.assertEqual(restarted.dialogue_history_for_actor("game-1", "A"), [("你好", "我看到了窗户")])
        self.assertEqual(restarted.dialogue_history_for_actor("game-1", "B"), [])


if __name__ == "__main__":
    unittest.main()
