import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_platform.generators.novel_narrator import NovelTurnNarrator, repeated_imagery
from storyloop_harness.advanced import Snapshot
from storyloop_platform.runtime.novel_presentation import present_freeform_novel
from storyloop_platform.runtime.campaign import CampaignProgram, CampaignSession
from storyloop_platform.runtime.novel_presentation import recover_last_freeform_novel
from storyloop_harness.advanced import SceneContext, StorySegment
from committed_input import commit_player_input
from storyloop_harness import ScenarioPackage


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "freeform"


class EscapedNewlineModel:
    async def __call__(self, prompt, **kwargs):
        return SimpleNamespace(metadata={"text": "你推开门。\\n\\n屋内传来谈话声。"})


class OddQuoteModel:
    async def __call__(self, prompt, **kwargs):
        return SimpleNamespace(metadata={"text": '你问了他一句。"\n他回答：“我愿意。”'})


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

    def test_novel_prose_removes_orphan_paragraph_quote(self):
        package = ScenarioPackage.load(EXAMPLE)
        context = SceneContext("game", "", Snapshot("game", 0, 0, {}),
                               (StorySegment("dialogue", "我愿意。"),), False, 1, "上午")
        prose = asyncio.run(NovelTurnNarrator(package, OddQuoteModel()).present(context))
        self.assertEqual(prose, "你问了他一句。\n他回答：“我愿意。”")

    def test_novel_prompt_and_fallback_address_the_player_as_you(self):
        package = ScenarioPackage.load(EXAMPLE)
        model = FailingNovelModel()
        context = SceneContext("game", "我打招呼", Snapshot("game", 0, 0, {}),
                               (StorySegment("dialogue", "早上好", "dockhand", "码头工"),),
                               False, 1, "上午")
        prose = asyncio.run(NovelTurnNarrator(package, model).present(context))
        self.assertIn("第二人称", str(model.prompt))
        self.assertEqual(prose, "你听见码头工的回应：早上好")

    def test_novel_prompt_uses_recent_prose_to_avoid_repeated_motifs(self):
        package = ScenarioPackage.load(EXAMPLE)
        model = FailingNovelModel()
        context = SceneContext("game", "你问他愿不愿意出门", Snapshot("game", 0, 0, {}),
                               (StorySegment("dialogue", "我愿意。", "dockhand", "码头工"),),
                               False, 1, "下午")
        asyncio.run(NovelTurnNarrator(
            package, model, recent_prose=lambda _: ["上午的光照着窗外的雪。",
                                                     "窗边的雪光很亮。"]
        ).present(context))
        self.assertIn("上午的光照着窗外的雪", str(model.prompt))
        self.assertIn("不要复述", str(model.prompt))
        self.assertIn("avoid_repeated_imagery", str(model.prompt))
        self.assertIn("dialogue_only", str(model.prompt))
        self.assertIn("80至140字", str(model.prompt))
        self.assertEqual(repeated_imagery(["上午的光照着窗外的雪。", "窗边的雪光很亮。"]),
                         ["光线与明暗", "窗与玻璃", "雪景"])


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
            beats = (StorySegment("dialogue", "早上好", "dockhand", "码头工"),)

            first = asyncio.run(present_freeform_novel(store, package, presenter, "game", "你好", "turn-1", beats))
            replay = asyncio.run(present_freeform_novel(store, package, presenter, "game", "你好", "turn-1", beats))

            self.assertEqual(first, replay)
            self.assertEqual(len(presenter.calls), 1)
            self.assertEqual(store.event_details("game", "turn-1:novel")["text"], first[0])
            self.assertEqual(store.observations_for("game", "player"), [])

    def test_terminal_recovery_finishes_committed_novel_turn_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "story.sqlite3"))
            package = ScenarioPackage.load(EXAMPLE)
            package.seed_game(store, "game")
            commit_player_input(store, "game", "turn-1:input", "你好")
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
