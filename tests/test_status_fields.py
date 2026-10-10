"""Scenario-owned status values remain authoritative across saves and turns."""

import unittest
import tempfile
from pathlib import Path

from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_harness.advanced import Observation, Snapshot, WorldEvent
from storyloop_platform.runtime.status_update import settle_status
from storyloop_platform.gameplay.presentation import turn_view
from storyloop_platform.runtime.guidance import GuidanceResult
from scenario_fixtures import loaded_status_fields


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


    def test_portal_view_projects_only_declared_player_visible_status(self) -> None:
        fields = loaded_status_fields(self.declarations + [
            {"id": "secret", "label": "隐藏状态", "path": ["relationships", "a", "met"],
             "visible": False},
        ], self.state)
        view = turn_view("game", "scenario", "freeform", "", Snapshot("game", 0, 0, self.state),
                                  GuidanceResult((), "test"), status_fields=fields)
        self.assertEqual([item["id"] for item in view["status_fields"]], ["mood", "location"])


    def test_status_update_is_event_sourced_and_idempotent(self) -> None:
        fields = loaded_status_fields(self.declarations, self.state)

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
