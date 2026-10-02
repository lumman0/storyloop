import asyncio
import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from story_harness.agents.scene_narrator import CampaignSceneNarrator
from story_harness.core.contracts import Snapshot
from story_harness.runtime.campaign import CampaignProgram, SceneContext
from story_harness.runtime.presentation import StorySegment
from story_harness.world.scenario import ScenarioPackage
from story_harness.world.worldbook import Worldbook, WorldbookEntry


class SceneNarratorTests(unittest.TestCase):
    def test_opening_uses_public_setting_and_visible_choices_without_secrets(self):
        package = ScenarioPackage.load(Path(__file__).resolve().parents[1] / "examples" / "freeform")
        book = Worldbook("sample", "1", [
            WorldbookEntry("house", "公开的雪夜别墅", "public", frozenset()),
            WorldbookEntry("secret", "隐藏的角色真相", "secret", frozenset()),
        ])
        package = replace(package, worldbook=book, opening="公开的节目开场")
        program = CampaignProgram.from_dict({
            "id": "sample", "ticks_per_day": 2, "final_tick": 2,
            "steps": [
                {"id": "intro", "at": 0, "kind": "scene", "text": "大家来到别墅"},
                {"id": "wish", "at": 0, "kind": "choice", "prompt": "愿望",
                 "options": [{"id": "friendship", "label": "认真认识一个人"}]},
                {"id": "end", "at": 2, "kind": "finale", "choice_key": "wish",
                 "threshold": 1, "success_text": "结束", "other_text": "结束"},
            ],
        })

        class Model:
            async def __call__(self, prompt, **kwargs):
                self.prompt = prompt
                return SimpleNamespace(metadata={"text": "雪夜的别墅正等着你。可以先看看四周，再与在场的人打招呼。"})

        model = Model()
        snapshot = Snapshot("g", 0, 0, {
            "actors": {"player": {"location": "house"}},
            "campaign": {"choices": {"wish": "friendship"}, "met": {}},
        })
        context = SceneContext("g", "/choose friendship", snapshot,
                               (StorySegment("choice", "已选择：认真认识一个人"),),
                               True, 1, "上午")
        result = asyncio.run(CampaignSceneNarrator(package, program, model).present(context))
        self.assertIn("可以先看看四周", result)
        prompt = json.dumps(model.prompt, ensure_ascii=False)
        self.assertIn("公开的雪夜别墅", prompt)
        self.assertIn("认真认识一个人", prompt)
        self.assertNotIn("隐藏的角色真相", prompt)
        self.assertNotIn("/choose friendship", prompt)
