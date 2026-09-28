import json
import tempfile
import unittest
from pathlib import Path

from story_harness.world.scenario import ScenarioPackage
from story_harness.adapters.store import SQLiteGameStore


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class ScenarioPackageTests(unittest.TestCase):
    def test_both_source_modes_load_and_seed_isolated_games(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "games.sqlite3"))
            for name, expected_unit in (("freeform", "slot"), ("scheduled", "slot")):
                package = ScenarioPackage.load(EXAMPLES / name)
                self.assertEqual(package.time_unit, expected_unit)
                self.assertEqual(package.ticks_per_day, 4)
                self.assertEqual(package.worldbook.package_id, package.package_id)
                self.assertTrue(package.worldbook.get(package.actor_cards[0][1], package.actor_cards[0][0]))
                game_id = f"game-{name}"
                package.seed_game(store, game_id)
                self.assertEqual(store.load(game_id).data["scenario"]["id"], package.package_id)
                self.assertEqual(store.load(game_id).data["scenario"]["version"], package.version)

            self.assertNotEqual(
                store.load("game-freeform").data["scenario"]["id"],
                store.load("game-scheduled").data["scenario"]["id"],
            )

    def test_invalid_worldbook_reference_or_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "worldbook.json").write_text(
                json.dumps({"package_id": "sample", "version": "1", "entries": []}),
                encoding="utf-8",
            )
            manifest = {
                "id": "sample", "version": "1", "time_unit": "day",
                "worldbook": "../outside.json", "actors": [], "initial_state": {},
                "initial_work": [],
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inside the package"):
                ScenarioPackage.load(root)

            manifest["worldbook"] = "worldbook.json"
            manifest["actors"] = [{"id": "A", "card": "missing"}]
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "card"):
                ScenarioPackage.load(root)

    def test_conflicting_or_duplicate_package_declarations_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "worldbook.json").write_text(
                json.dumps({"package_id": "wrong", "version": "1", "entries": []}),
                encoding="utf-8",
            )
            manifest = {
                "id": "sample", "version": "1", "time_unit": "day",
                "worldbook": "worldbook.json", "actors": [], "initial_state": {},
                "initial_work": [],
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identity"):
                ScenarioPackage.load(root)

            worldbook = json.loads((root / "worldbook.json").read_text(encoding="utf-8"))
            worldbook["package_id"] = "sample"
            (root / "worldbook.json").write_text(json.dumps(worldbook), encoding="utf-8")
            manifest["initial_work"] = [
                {"id": "repeat", "kind": "cue", "due_tick": 1, "priority": 0, "payload": {}},
                {"id": "repeat", "kind": "cue", "due_tick": 2, "priority": 0, "payload": {}},
            ]
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate work"):
                ScenarioPackage.load(root)

    def test_scheduled_effect_must_target_declared_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "worldbook.json").write_text(
                json.dumps({"package_id": "sample", "version": "1", "entries": []}),
                encoding="utf-8",
            )
            manifest = {
                "id": "sample", "version": "1", "time_unit": "day",
                "worldbook": "worldbook.json", "actors": [],
                "initial_state": {"world": {"stage": "opening"}},
                "initial_work": [{
                    "id": "cue", "kind": "scenario_cue", "due_tick": 1, "priority": 0,
                    "payload": {"event_kind": "next", "summary": "下一幕", "effect_path": ["world", "missing"], "effect_value": "next"},
                }],
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown effect path"):
                ScenarioPackage.load(root)


if __name__ == "__main__":
    unittest.main()
