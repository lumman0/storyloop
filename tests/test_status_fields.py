"""Scenario-owned status values remain authoritative across saves and turns."""

import unittest
import tempfile
from pathlib import Path

from story_harness.adapters.store import SQLiteGameStore
from story_harness.core.contracts import Observation, Snapshot, WorldEvent
from story_harness.runtime.status_update import settle_status
from story_harness.portal.service import PlayerPortal
from story_harness.runtime.guidance import GuidanceResult
from story_harness.world.status_fields import parse_status_fields, project_status_fields, status_effects


class StatusFieldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {
            "actors": {"player": {"location": "villa"}},
            "relationships": {"a": {"met": False, "affinity": 0}},
            "player_stats": {"mood": 80},
        }
        self.declarations = [
            {"id": "mood", "label": "心情值", "path": ["player_stats", "mood"],
             "bounds": {"min": 0, "max": 100, "max_delta": 3}},
            {"id": "affinity_a", "label": "与甲的好感度",
             "path": ["relationships", "a", "affinity"],
             "when": {"path": ["relationships", "a", "met"], "equals": True},
             "bounds": {"min": 0, "max": 100, "max_delta": 2}},
            {"id": "location", "label": "当前位置", "path": ["actors", "player", "location"]},
        ]

    def test_projection_respects_visibility_and_knowledge_gate(self) -> None:
        fields = parse_status_fields(self.declarations, self.state)
        self.assertEqual(project_status_fields(fields, self.state), [
            {"id": "mood", "label": "心情值", "value": 80, "min": 0, "max": 100},
            {"id": "location", "label": "当前位置", "value": "villa"},
        ])
        self.state["relationships"]["a"]["met"] = True
        self.assertEqual(project_status_fields(fields, self.state)[1]["value"], 0)
        self.assertEqual([item["id"] for item in project_status_fields(
            fields, {"player_stats": {"mood": 80}, "actors": self.state["actors"]})],
            ["mood", "location"])

    def test_deltas_are_bounded_and_only_declared_fields_can_change(self) -> None:
        fields = parse_status_fields(self.declarations, self.state)
        snapshot = Snapshot("game", 0, 0, self.state)
        effects = status_effects(fields, snapshot, [{"id": "mood", "delta": -2}])
        self.assertEqual(effects[0].path, ("player_stats", "mood"))
        self.assertEqual(effects[0].value, 78)
        with self.assertRaisesRegex(ValueError, "delta"):
            status_effects(fields, snapshot, [{"id": "mood", "delta": 12}])
        with self.assertRaisesRegex(ValueError, "unknown"):
            status_effects(fields, snapshot, [{"id": "location", "delta": 1}])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            status_effects(fields, snapshot, [{"id": "mood", "delta": 1},
                                             {"id": "mood", "delta": 1}])

    def test_portal_view_projects_only_declared_player_visible_status(self) -> None:
        fields = parse_status_fields(self.declarations + [
            {"id": "secret", "label": "隐藏状态", "path": ["relationships", "a", "met"],
             "visible": False},
        ], self.state)
        view = PlayerPortal._view("game", "scenario", "freeform", "", Snapshot("game", 0, 0, self.state),
                                  GuidanceResult((), "test"), status_fields=fields)
        self.assertEqual([item["id"] for item in view["status_fields"]], ["mood", "location"])

    def test_invalid_status_schema_fails_on_package_load(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown"):
            parse_status_fields([{"id": "x", "label": "X", "path": ["missing"]}], self.state)
        with self.assertRaisesRegex(ValueError, "bounds"):
            parse_status_fields([{"id": "location", "label": "位置",
                                  "path": ["actors", "player", "location"],
                                  "bounds": {"min": 0, "max": 100, "max_delta": 2}}], self.state)

    def test_status_update_is_event_sourced_and_idempotent(self) -> None:
        fields = parse_status_fields(self.declarations, self.state)

        async def propose(_snapshot, _text, evidence, _fields):
            self.assertEqual(evidence, ("甲邀请玩家一起散步",))
            return [{"id": "mood", "delta": 2}]

        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
                store.create_game(Snapshot("game", 0, 0, self.state), ())
                event = WorldEvent("turn:input", "player_input", "player", None, 1, ())
                observation = Observation("turn:seen", "turn:input", "player", "scene",
                                          "甲邀请玩家一起散步", 1)
                store.commit("game", 0, event, (observation,), ())
                first = await settle_status(store, "game", "turn", "我答应了", fields,
                                            (observation,), propose)
                second = await settle_status(store, "game", "turn", "我答应了", fields,
                                             (observation,), propose)
                self.assertEqual(first.data["player_stats"]["mood"], 82)
                self.assertEqual(second.version, first.version)
                self.assertEqual(store.event_details("game", "turn:status")["changes"],
                                 [{"id": "mood", "delta": 2}])

        import asyncio
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
