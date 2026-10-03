import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from story_harness.adapters.store import SQLiteGameStore
from story_harness.agents.action_advisor import ActionOptionAdvisor
from story_harness.agents.novel_narrator import NovelTurnNarrator
from story_harness.core.contracts import Snapshot
from story_harness.portal.service import PlayerPortal
from story_harness.runtime.campaign import CampaignProgram, CampaignSession
from story_harness.runtime.novel_presentation import recover_last_freeform_novel
from story_harness.runtime.presentation import SceneContext, StorySegment
from story_harness.runtime.player_input import submit_player_input
from story_harness.world.scenario import ScenarioPackage


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "freeform"


class FakeOptionModel:
    def __init__(self):
        self.calls = 0

    async def __call__(self, prompt, **kwargs):
        self.calls += 1
        return SimpleNamespace(metadata={"options": [
            {"label": "看看四周", "input": "我观察周围。"},
            {"label": "和人交谈", "input": "我找在场的人聊聊。"},
            {"label": "试着行动", "input": "我参与眼前的事情。"},
        ]})


class BlankOptionModel(FakeOptionModel):
    async def __call__(self, prompt, **kwargs):
        response = await super().__call__(prompt, **kwargs)
        response.metadata["options"][0]["input"] = "   "
        return response


class EscapedNewlineModel:
    async def __call__(self, prompt, **kwargs):
        return SimpleNamespace(metadata={"text": "你推开门。\\n\\n屋内传来谈话声。"})


class FailingNovelModel:
    def __init__(self):
        self.prompt = None

    async def __call__(self, prompt, **kwargs):
        self.prompt = prompt
        raise RuntimeError("offline")


class FakeNovelPresenter:
    def __init__(self):
        self.calls = []

    async def present(self, context):
        self.calls.append(context)
        return "你看见客厅的灯亮起来，故事从这里开始。"


class PresentationModeTests(unittest.TestCase):
    def test_novel_prose_decodes_literal_model_line_breaks(self):
        package = ScenarioPackage.load(EXAMPLE)
        context = SceneContext("game", "", Snapshot("game", 0, 0, {}),
                               (StorySegment("scene", "门打开了。"),), True, 1, "上午")
        prose = asyncio.run(NovelTurnNarrator(package, EscapedNewlineModel()).present(context))
        self.assertEqual(prose, "你推开门。\n\n屋内传来谈话声。")

    def test_novel_prompt_and_fallback_address_the_player_as_you(self):
        package = ScenarioPackage.load(EXAMPLE)
        model = FailingNovelModel()
        context = SceneContext("game", "我打招呼", Snapshot("game", 0, 0, {}),
                               (StorySegment("dialogue", "早上好", "dockhand", "码头工"),),
                               False, 1, "上午")
        prose = asyncio.run(NovelTurnNarrator(package, model).present(context))
        self.assertIn("第二人称", str(model.prompt))
        self.assertEqual(prose, "你听见码头工的回应：早上好")

    def test_manifest_defaults_to_interactive_and_accepts_novel(self):
        self.assertEqual(ScenarioPackage.load(EXAMPLE).presentation_mode, "interactive")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for name in ("manifest.json", "worldbook.json"):
                (target / name).write_bytes((EXAMPLE / name).read_bytes())
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            manifest["presentation_mode"] = "novel"
            (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(ScenarioPackage.load(target).presentation_mode, "novel")

    def test_action_advisor_makes_one_model_call_for_three_clickable_actions(self):
        model = FakeOptionModel()
        options = asyncio.run(ActionOptionAdvisor(model).suggest("灯亮了。", "novel"))
        self.assertEqual(model.calls, 1)
        self.assertEqual(len(options), 3)
        self.assertEqual(options[0].input, "我观察周围。")

    def test_blank_model_action_uses_three_executable_fallbacks(self):
        model = BlankOptionModel()
        options = asyncio.run(ActionOptionAdvisor(model).suggest("灯亮了。", "novel"))
        self.assertEqual(model.calls, 1)
        self.assertEqual(len(options), 3)
        self.assertTrue(all(option.label.strip() and option.input.strip() for option in options))

    def test_campaign_leads_replace_actions_unrelated_to_visible_story(self):
        model = FakeOptionModel()
        leads = [
            {"label": "交还行李牌", "input": "我把行李牌交给刚认识的嘉宾。"},
            {"label": "问节目安排", "input": "我问节目组今晚有什么共同环节。"},
            {"label": "加入晚餐准备", "input": "我到客厅帮大家准备晚餐。"},
        ]
        options = asyncio.run(ActionOptionAdvisor(model).suggest(
            "嘉宾们在客厅等着。", "interactive",
            story_context={"goal": "认识嘉宾", "anchors": ["行李牌", "节目组", "晚餐"],
                           "leads": leads},
        ))
        self.assertEqual(model.calls, 1)
        self.assertEqual([option.label for option in options], [lead["label"] for lead in leads])

    def test_authored_fallback_never_repeats_a_completed_action(self):
        leads = [
            {"label": "问报名缘由", "input": "我问周闻野为什么报名。"},
            {"label": "了解节目安排", "input": "我问节目组今晚有什么安排。"},
            {"label": "加入晚餐准备", "input": "我去帮大家准备晚餐。"},
        ]
        options = asyncio.run(ActionOptionAdvisor(FakeOptionModel()).suggest(
            "周闻野刚回答了报名原因。", "novel",
            story_context={"anchors": ["周闻野", "节目组", "晚餐"], "leads": leads},
            recent_actions=(leads[0]["input"],),
        ))
        self.assertEqual([item.input for item in options],
                         [leads[1]["input"], leads[2]["input"]])

    def test_novel_campaign_stores_single_prose_and_reuses_it_on_retry(self):
        program = CampaignProgram.from_dict({
            "id": "test-novel", "ticks_per_day": 2, "final_tick": 2,
            "steps": [
                {"id": "pick", "at": 0, "kind": "choice", "prompt": "选择",
                 "options": [{"id": "a", "label": "甲"}]},
                {"id": "opening", "at": 0, "kind": "scene", "text": "客厅灯亮了。"},
                {"id": "ending", "at": 2, "kind": "finale", "choice_key": "pick",
                 "threshold": 1, "success_text": "结束", "other_text": "结束"},
            ],
        })
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "story.sqlite3"))
            store.create_game(Snapshot("game", 0, 0, {
                "scenario": {"id": "test-novel", "version": "1"},
                "actors": {"player": {"location": "room"}},
                "campaign": program.initial_state([]),
            }))
            presenter = FakeNovelPresenter()
            session = CampaignSession(store, program, novel_presenter=presenter)
            result = asyncio.run(session.submit("game", "/choose a", "turn-1"))
            self.assertEqual([part.kind for part in result.segments], ["narration"])
            self.assertEqual(result.text, "你看见客厅的灯亮起来，故事从这里开始。")
            self.assertEqual(len(presenter.calls), 1)
            replay = asyncio.run(session.submit("game", "/choose a", "turn-1"))
            self.assertEqual(replay.text, result.text)
            self.assertEqual(len(presenter.calls), 1)

    def test_novel_campaign_presents_initial_scene_and_scene_between_gates(self):
        program = CampaignProgram.from_dict({
            "id": "novel-gates", "ticks_per_day": 2, "final_tick": 2,
            "steps": [
                {"id": "arrival", "at": 0, "kind": "scene", "text": "门开了。"},
                {"id": "first", "at": 0, "kind": "choice", "prompt": "选一个",
                 "options": [{"id": "a", "label": "甲"}]},
                {"id": "between", "at": 0, "kind": "scene", "text": "灯亮了。"},
                {"id": "second", "at": 0, "kind": "choice", "prompt": "再选一个",
                 "options": [{"id": "b", "label": "乙"}]},
                {"id": "end", "at": 2, "kind": "finale", "choice_key": "first",
                 "threshold": 1, "success_text": "结束", "other_text": "结束"},
            ],
        })
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "story.sqlite3"))
            store.create_game(Snapshot("game", 0, 0, {
                "scenario": {"id": "novel-gates", "version": "1"},
                "actors": {"player": {"location": "room"}},
                "campaign": program.initial_state([]),
            }))
            presenter = FakeNovelPresenter()
            session = CampaignSession(store, program, novel_presenter=presenter)

            opening = asyncio.run(session.start("game"))
            self.assertEqual([part.kind for part in opening.segments], ["narration", "prompt"])
            self.assertTrue(store.event_exists("game", "campaign:opening:novel"))
            opening_replay = asyncio.run(session.start("game"))
            self.assertEqual(opening_replay.text, opening.text)
            self.assertEqual(len(presenter.calls), 1)
            next_gate = asyncio.run(session.submit("game", "/choose a", "turn-1"))
            self.assertEqual(next_gate.gate_id, "second")
            self.assertEqual([part.kind for part in next_gate.segments], ["narration", "prompt"])
            self.assertTrue(store.event_exists("game", "turn-1:novel"))
            self.assertEqual(len(presenter.calls), 2)

    def test_freeform_novel_prose_is_recoverable_without_becoming_an_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "story.sqlite3"))
            package = ScenarioPackage.load(EXAMPLE)
            package.seed_game(store, "game")
            presenter = FakeNovelPresenter()
            portal = PlayerPortal.__new__(PlayerPortal)
            portal.store = store
            portal._novel_presenter = lambda _package, _game_id: presenter
            beats = (StorySegment("dialogue", "早上好", "dockhand", "码头工"),)

            first = asyncio.run(portal._freeform_novel(package, "game", "你好", "turn-1", beats))
            replay = asyncio.run(portal._freeform_novel(package, "game", "你好", "turn-1", beats))

            self.assertEqual(first, replay)
            self.assertEqual(len(presenter.calls), 1)
            self.assertEqual(store.event_details("game", "turn-1:novel")["text"], first[0])
            self.assertEqual(store.observations_for("game", "player"), [])

    def test_terminal_recovery_finishes_committed_novel_turn_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "story.sqlite3"))
            package = ScenarioPackage.load(EXAMPLE)
            package.seed_game(store, "game")
            submit_player_input(store, "game", "turn-1:input", "你好")
            presenter = FakeNovelPresenter()
            resumed = []

            async def ready(game_id):
                resumed.append(game_id)

            first = asyncio.run(recover_last_freeform_novel(
                store, package, presenter, "game", ready,
            ))
            replay = asyncio.run(recover_last_freeform_novel(
                store, package, presenter, "game", ready,
            ))

            self.assertEqual(first, replay)
            self.assertEqual(resumed, ["game"])
            self.assertEqual(len(presenter.calls), 1)
            self.assertEqual(store.event_details("game", "turn-1:novel")["text"], first)


if __name__ == "__main__":
    unittest.main()
