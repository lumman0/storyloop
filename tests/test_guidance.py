import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_platform.cli.guidance_view import format_guidance, format_turn_output
from storyloop_harness.core.contracts import Snapshot
from storyloop_platform.runtime.campaign import CampaignProgram
from storyloop_platform.runtime.guidance import GuidanceAdvisor, GuidanceResult
from storyloop_harness.world.scenario import ScenarioPackage


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "freeform"


class GuidanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteGameStore(str(Path(self.temp.name) / "guide.sqlite3"))
        self.package = ScenarioPackage.load(EXAMPLE)
        self.program = CampaignProgram.from_dict({
            "id": self.package.package_id, "ticks_per_day": 4, "final_tick": 4,
            "steps": [
                {"id": "first_choice", "at": 0, "kind": "choice", "prompt": "选择下一步的方向",
                 "options": [{"id": "look", "label": "观察"}]},
                {"id": "ending", "at": 4, "kind": "finale", "choice_key": "first_choice",
                 "threshold": 1, "success_text": "完成", "other_text": "结束"},
            ],
        })
        state = dict(self.package.initial_state)
        state["scenario"] = {"id": self.package.package_id, "version": self.package.version}
        state["campaign"] = self.program.initial_state(["dockhand"])
        self.store.create_game(Snapshot("campaign", 0, 0, state))
        self.package.seed_game(self.store, "freeform")

    async def test_due_choice_guidance_is_separate_and_does_not_commit_state(self) -> None:
        before = self.store.load("campaign")
        advisor = GuidanceAdvisor(self.store, self.package, self.program)

        result = await advisor.advise("campaign", before, gate_id="first_choice")

        self.assertEqual(len(result.items), 1)
        self.assertIn("选择下一步的方向", result.items[0])
        self.assertIn("/choose", result.items[0])
        self.assertEqual(self.store.load("campaign"), before)
        self.assertTrue(format_guidance(result).startswith("── 下一步建议 ──\n• "))

    async def test_open_campaign_uses_nearby_people_and_progress_without_spoilers(self) -> None:
        advisor = GuidanceAdvisor(self.store, self.package, self.program)
        state = self.store.load("campaign").data
        state["campaign"]["cursor"] = 1
        snapshot = Snapshot("campaign", 1, 1, state)

        result = await advisor.advise("campaign", snapshot,
                                      visible_text="【码头工】\n我正在广场整理用具。")

        self.assertEqual(len(result.items), 2)
        self.assertIn("码头工", result.items[0])
        self.assertIn("/next", result.items[1])
        self.assertNotIn("结局", format_guidance(result))

    async def test_late_campaign_guidance_reflects_progress_without_revealing_ending(self) -> None:
        advisor = GuidanceAdvisor(self.store, self.package, self.program)
        snapshot = Snapshot("campaign", 1, 4, self.store.load("campaign").data)

        result = await advisor.advise("campaign", snapshot)

        self.assertIn("接近尾声", result.items[0])
        self.assertNotIn("完成", result.items[0])
        self.assertNotIn("结束", result.items[0])

    async def test_plain_turn_engine_game_gets_actionable_suggestions(self) -> None:
        advisor = GuidanceAdvisor(self.store, self.package)

        result = await advisor.advise("freeform", self.store.load("freeform"),
                                      visible_text="【码头工】\n你好，来港口看看吧。")

        self.assertTrue(any("码头工" in item for item in result.items))
        self.assertFalse(any("/next" in item for item in result.items))

    async def test_unobserved_actor_is_not_revealed_by_global_location_state(self) -> None:
        hidden_package = replace(self.package, opening="你来到港口广场。有人说码头工今天不在。")
        advisor = GuidanceAdvisor(self.store, hidden_package)

        result = await advisor.advise("freeform", self.store.load("freeform"),
                                      visible_text=hidden_package.opening)

        self.assertFalse(any("码头工" in item for item in result.items))

    async def test_message_gate_explains_the_required_message_format(self) -> None:
        program = CampaignProgram.from_dict({
            "id": self.package.package_id, "ticks_per_day": 4, "final_tick": 4,
            "steps": [
                {"id": "first_choice", "at": 0, "kind": "choice", "prompt": "出发方向",
                 "options": [{"id": "look", "label": "观察"}]},
                {"id": "leave_note", "at": 1, "kind": "message", "prompt": "写一条留言",
                 "options": [{"id": "skip", "label": "不留言"},
                             {"id": "dockhand", "label": "码头工", "recipient": "dockhand"}]},
                {"id": "ending", "at": 4, "kind": "finale", "choice_key": "first_choice",
                 "threshold": 1, "success_text": "完成", "other_text": "结束"},
            ],
        })
        advisor = GuidanceAdvisor(self.store, self.package, program)
        state = self.store.load("campaign").data
        state["campaign"]["cursor"] = 1
        snapshot = Snapshot("campaign", 1, 1, state)

        result = await advisor.advise("campaign", snapshot, gate_id="leave_note")

        self.assertIn("/choose 选项ID 留言内容", result.items[0])
        self.assertIn("skip", result.items[0])

    async def test_empty_gate_prompt_still_blocks_free_action_advice(self) -> None:
        step = {**self.program.steps[0], "prompt": ""}
        advisor = GuidanceAdvisor(self.store, self.package,
                                  replace(self.program, steps=(step, self.program.steps[1])))

        result = await advisor.advise("campaign", self.store.load("campaign"),
                                      gate_id="first_choice")

        self.assertIn("/choose", result.items[0])
        self.assertFalse(any("/next" in item for item in result.items))

    async def test_malformed_provider_output_falls_back(self) -> None:
        class MalformedProvider:
            def __init__(self, value):
                self.value = value

            async def suggest(self, context):
                return self.value

        before = self.store.load("freeform")
        for invalid in ("文字不是建议列表", (item for item in ("一", "二"))):
            with self.subTest(output=type(invalid).__name__):
                advisor = GuidanceAdvisor(self.store, self.package,
                                          provider=MalformedProvider(invalid))
                result = await advisor.advise("freeform", before)
                self.assertEqual(result.source, "fallback")
                self.assertEqual(self.store.load("freeform"), before)

    async def test_provider_failure_falls_back_without_changing_game(self) -> None:
        class BrokenProvider:
            async def suggest(self, context):
                raise RuntimeError("temporary suggestion failure")

        before = self.store.load("freeform")
        advisor = GuidanceAdvisor(self.store, self.package, provider=BrokenProvider())

        result = await advisor.advise("freeform", before)

        self.assertTrue(result.items)
        self.assertEqual(result.source, "fallback")
        self.assertEqual(self.store.load("freeform"), before)

    async def test_turn_output_keeps_recommendations_outside_story_body(self) -> None:
        guidance = GuidanceResult(("可以和码头工交谈。", "也可以观察周围。"), "provider")

        rendered = format_turn_output("【码头工】\n你好。", "[tick 1]", guidance)

        self.assertEqual(rendered, "【码头工】\n你好。\n[tick 1]\n\n"
                         "── 下一步建议 ──\n• 可以和码头工交谈。\n• 也可以观察周围。")


if __name__ == "__main__":
    unittest.main()
