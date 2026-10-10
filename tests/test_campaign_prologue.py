"""A scenario can reveal authored opening scenes before asking for a choice."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_harness.advanced import Snapshot
from storyloop_platform.portal.presentation import campaign_interaction
from storyloop_platform.runtime.campaign import CampaignProgram, CampaignSession


class CampaignPrologueTests(unittest.TestCase):
    def test_continue_reveals_next_scene_without_time_or_agent_call(self):
        program = CampaignProgram.from_dict({
            "id": "prologue", "ticks_per_day": 2, "final_tick": 2,
            "steps": [
                {"id": "arrival", "at": 0, "kind": "scene", "text": "雪落在门前。"},
                {"id": "enter", "at": 0, "kind": "continue", "prompt": "门内有人。", "label": "推门进去"},
                {"id": "cast", "at": 0, "kind": "scene", "text": "你认识了甲和乙。"},
                {"id": "badge", "at": 0, "kind": "choice", "prompt": "交给谁？",
                 "options": [{"id": "a", "label": "甲"}, {"id": "b", "label": "乙"}]},
                {"id": "ending", "at": 2, "kind": "finale", "choice_key": "badge",
                 "threshold": 1, "success_text": "结局", "other_text": "结局"},
            ],
        })
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            store.create_game(Snapshot("game", 0, 0, {
                "scenario": {"id": "prologue", "version": "1"},
                "campaign": program.initial_state(["a", "b"]),
                "actors": {"player": {"location": "house"}},
            }))
            session = CampaignSession(store, program)
            opening = asyncio.run(session.start("game"))
            self.assertEqual(opening.gate_id, "enter")
            self.assertIn("雪落在门前", opening.text)
            self.assertNotIn("认识了甲", opening.text)
            self.assertEqual(campaign_interaction(program, opening.snapshot, opening.gate_id), {
                "id": "enter", "kind": "continue", "prompt": "门内有人。",
                "label": "推门进去", "options": [],
            })

            blocked = asyncio.run(session.submit("game", "你好", "blocked"))
            self.assertEqual(blocked.gate_id, "enter")
            self.assertEqual(store.load("game").data["campaign"]["cursor"], 1)

            revealed = asyncio.run(session.submit("game", "/continue", "enter-turn"))
            self.assertEqual(revealed.gate_id, "badge")
            self.assertEqual(revealed.snapshot.tick, 0)
            self.assertIn("认识了甲和乙", revealed.text)
            self.assertEqual(revealed.snapshot.data["campaign"]["cursor"], 3)

            replayed = asyncio.run(session.submit("game", "/continue", "enter-turn"))
            self.assertEqual(replayed.text, revealed.text)
            self.assertEqual(replayed.snapshot.tick, 0)
            self.assertEqual(len(store.player_inputs_for("game")), 0)

    def test_continue_requires_readable_prompt_and_button(self):
        base = {"id": "prologue", "ticks_per_day": 1, "final_tick": 1,
                "steps": [{"id": "enter", "at": 0, "kind": "continue",
                           "prompt": " ", "label": "下一幕"},
                          {"id": "badge", "at": 0, "kind": "choice", "prompt": "选谁",
                           "options": [{"id": "a", "label": "甲"}]},
                          {"id": "end", "at": 1, "kind": "finale", "choice_key": "badge",
                           "threshold": 0, "success_text": "结束", "other_text": "结束"}]}
        with self.assertRaisesRegex(ValueError, "continue requires prompt and label"):
            CampaignProgram.from_dict(base)


if __name__ == "__main__":
    unittest.main()
