import tempfile
import unittest
from pathlib import Path

from storyloop_harness.core.actions import adjudicate_action
from storyloop_harness.core.perception import physical_observations
from storyloop_harness.world.scenario import ScenarioPackage
from storyloop_platform.adapters.store import SQLiteGameStore


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "freeform"


class ActionTests(unittest.TestCase):
    def test_declared_action_changes_world_and_only_witnesses_learn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage.load(EXAMPLE)
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            before = store.load("game")
            rule = package.action_rules["break_shop_window"]

            event, direct = adjudicate_action(before, rule, "action-1", "我打破橱窗")
            after = store.commit("game", before.version, event, direct + physical_observations(before, event), ())

            self.assertTrue(after.data["world"]["shop_window"]["broken"])
            self.assertEqual(len(store.observations_for("game", "dockhand")), 1)
            self.assertEqual(len(store.observations_for("game", "player")), 1)

    def test_repeat_action_does_not_break_an_already_broken_object_again(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage.load(EXAMPLE)
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            rule = package.action_rules["break_shop_window"]
            first = store.load("game")
            event, observations = adjudicate_action(first, rule, "action-1", "打破橱窗")
            store.commit("game", first.version, event, observations, ())

            second = store.load("game")
            event, observations = adjudicate_action(second, rule, "action-2", "再打破橱窗")
            after = store.commit("game", second.version, event, observations, ())

            self.assertEqual(event.kind, "action_rejected")
            self.assertEqual(after.data["world"]["shop_window"]["broken"], True)
            self.assertEqual(observations[0].recipient_id, "player")


if __name__ == "__main__":
    unittest.main()
