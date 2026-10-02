import tempfile
import json
import unittest
from pathlib import Path

from agentscope.model import ChatModelBase, ChatResponse

from story_harness.agents.npc_agent import NpcAgentPool
from story_harness.runtime.game_session import GameSession, compose_visible_narration, compose_visible_segments
from story_harness.core.contracts import Observation
from story_harness.agents.main_agent import MainDecision
from story_harness.world.scenario import ScenarioPackage
from story_harness.adapters.store import SQLiteGameStore
from story_harness.runtime.schedule import advance_time
from story_harness.runtime.story_clock import StoryClock


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "freeform"


class ReplyModel(ChatModelBase):
    def __init__(self) -> None:
        super().__init__(model_name="reply-test", stream=False)

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        return ChatResponse(content=[{"type": "text", "text": "A：我听见了。"}])


class ScriptedMain:
    def __init__(self, decision: MainDecision) -> None:
        self.decision = decision
        self.visible_results: list[str] = []

    async def decide(self, player_text: str) -> MainDecision:
        return self.decision

    async def summarize(self, player_text: str, visible_results: list[str]) -> str:
        self.visible_results = visible_results
        return "；".join(visible_results) if visible_results else "暂时没有可见变化。"


class GameSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteGameStore(str(Path(self.temp.name) / "game.sqlite3"))
        self.package = ScenarioPackage.load(EXAMPLE)
        self.package.seed_game(self.store, "game")
        self.pool = NpcAgentPool(self.store, lambda game_id, actor_id: ReplyModel())

    def session(self, main: ScriptedMain) -> GameSession:
        return GameSession(self.store, self.package, lambda game_id: main, self.pool, max_steps=8)

    async def test_ready_work_can_be_resumed_after_external_clock_advance(self) -> None:
        advance_time(self.store, "game", 4, "external-clock")
        session = self.session(ScriptedMain(MainDecision(intent="inspect")))
        result = await session.run_ready_work("game")
        self.assertIn("harbor-opening-cue", result.processed_work_ids)
        self.assertEqual(result.snapshot.data["world"]["market_phase"], "open")

    async def test_narration_keeps_dialogue_verbatim_in_event_order(self) -> None:
        seen: list[list[str]] = []

        async def summarize(_text: str, results: list[str]) -> str:
            seen.append(results)
            return "环境：" + "、".join(results)

        observations = (
            Observation("o1", "e1", "player", "action_result", "玻璃碎了", 1),
            Observation("o2", "e2", "player", "dialogue", "A：我看见了。", 1),
            Observation("o3", "e3", "player", "sensory", "钟声响了", 2),
        )
        result = await compose_visible_narration("我做了什么", observations, summarize)
        self.assertEqual(result, "环境：玻璃碎了\n\nA：我看见了。\n\n环境：钟声响了")
        self.assertEqual(seen, [["玻璃碎了"], ["钟声响了"]])

    async def test_speech_commits_player_input_npc_reply_and_visible_summary(self) -> None:
        main = ScriptedMain(MainDecision(intent="speech", target_ids=["dockhand"], channel="speech"))

        outcome = await self.session(main).run_turn("game", "你好", "turn-1")

        self.assertEqual(outcome.snapshot.tick, 1)
        self.assertEqual(self.store.player_inputs_for("game")[0].text, "你好")
        self.assertEqual(outcome.narration, "【码头工】\nA：我听见了。")
        self.assertEqual(main.visible_results, [])

    async def test_campaign_clock_uses_main_decision_duration(self) -> None:
        main = ScriptedMain(MainDecision(intent="speech", target_ids=[], duration="extended"))
        session = GameSession(self.store, self.package, lambda _game: main, self.pool,
                              max_steps=8, story_clock=StoryClock(6))
        result = await session.run_turn("game", "逛了一下午", "long")
        self.assertEqual(result.snapshot.tick, 3)
        self.assertEqual(self.store.event_details("game", "long:input")["duration"], "extended")
        main.decision = MainDecision(intent="speech", target_ids=[], duration="rest")
        result = await session.run_turn("game", "睡觉", "sleep")
        self.assertEqual(result.snapshot.tick, 6)

    async def test_private_message_remains_separate_from_narration(self) -> None:
        async def summarize(_text: str, results: list[str]) -> str:
            return "环境：" + "、".join(results)

        observations = (
            Observation("o1", "e1", "player", "scene", "雪停了", 1),
            Observation("o2", "e2", "player", "private_message", "今晚见", 1),
        )
        segments = await compose_visible_segments("我看看", observations, summarize)
        self.assertEqual([(item.kind, item.text) for item in segments],
                         [("narration", "环境：雪停了"), ("message", "今晚见")])

    async def test_group_speech_has_named_reply_blocks_and_all_nearby_npcs_hear_it(self) -> None:
        root = Path(self.temp.name) / "group"
        root.mkdir()
        (root / "worldbook.json").write_text(json.dumps({
            "package_id": "group", "version": "1", "entries": [
                {"id": "shared_card", "kind": "card", "visibility": "public", "text": "只说自己知道的事。"},
            ],
        }), encoding="utf-8")
        actors = [("a", "甲"), ("b", "乙"), ("c", "店员"), ("d", "店员"), ("e", "戊")]
        (root / "manifest.json").write_text(json.dumps({
            "id": "group", "version": "1", "time_unit": "tick", "worldbook": "worldbook.json",
            "actors": [{"id": actor_id, "name": name, "card": "shared_card"} for actor_id, name in actors],
            "initial_state": {"actors": {"player": {"location": "room"}} |
                              {actor_id: {"location": "room"} for actor_id, _ in actors}},
            "initial_work": [], "actions": [],
        }, ensure_ascii=False), encoding="utf-8")
        package = ScenarioPackage.load(root)
        package.seed_game(self.store, "group")
        main = ScriptedMain(MainDecision(intent="speech", audience="room",
                                        target_ids=[actor_id for actor_id, _ in actors]))
        session = GameSession(self.store, package, lambda _game: main, self.pool,
                              max_steps=8, max_npc_replies=2)

        result = await session.run_turn("group", "大家好呀", "group-turn")

        self.assertEqual(result.decision.target_ids, ["a", "b"])
        self.assertEqual(result.narration, "【甲】\nA：我听见了。\n\n【乙】\nA：我听见了。")
        self.assertEqual([(part.kind, part.speaker_id, part.speaker_name, part.text)
                          for part in result.segments], [
            ("dialogue", "a", "甲", "A：我听见了。"),
            ("dialogue", "b", "乙", "A：我听见了。"),
        ])
        self.assertEqual(len(result.player_observations), 2)
        self.assertEqual(result.processed_work_ids,
                         ("group-turn:input:reply:a", "group-turn:input:reply:b"))
        self.assertTrue(all(self.store.observations_for("group", actor_id)[0].content == "大家好呀"
                            for actor_id, _ in actors))

        main.decision = MainDecision(intent="speech", channel="private_message",
                                     target_ids=[actor_id for actor_id, _ in actors[:4]])
        private = await session.run_turn("group", "只告诉这四个人", "private-turn")
        self.assertEqual(len(private.player_observations), 4)
        self.assertEqual(private.decision.target_ids, ["a", "b", "c", "d"])
        self.assertIn("【店员 (c)】", private.narration)
        self.assertIn("【店员 (d)】", private.narration)
        self.assertTrue(all(any(item.content == "只告诉这四个人"
                                for item in self.store.observations_for("group", actor_id))
                            for actor_id, _ in actors[:4]))
        self.assertFalse(any(item.content == "只告诉这四个人"
                             for item in self.store.observations_for("group", "e")))

        main.decision = MainDecision(intent="speech", target_ids=["a"])
        await session.run_turn("group", "只对甲说的普通话", "targeted-turn")
        self.assertTrue(any(item.content == "只对甲说的普通话"
                            for item in self.store.observations_for("group", "a")))
        self.assertFalse(any(item.content == "只对甲说的普通话"
                             for item in self.store.observations_for("group", "e")))

    async def test_action_changes_tracked_window_then_repeat_is_rejected(self) -> None:
        main = ScriptedMain(MainDecision(intent="action", action_id="break_shop_window"))
        session = self.session(main)

        first = await session.run_turn("game", "我打破橱窗", "turn-1")
        second = await session.run_turn("game", "我再打一次", "turn-2")

        self.assertTrue(first.snapshot.data["world"]["shop_window"]["broken"])
        self.assertTrue(second.snapshot.data["world"]["shop_window"]["broken"])
        self.assertEqual(len(self.store.observations_for("game", "dockhand")), 1)
        self.assertIn("不允许重复", second.narration)
        self.assertEqual([item.text for item in self.store.player_inputs_for("game")], ["我打破橱窗", "我再打一次"])

    async def test_inspect_is_free_and_cannot_read_secret_entry(self) -> None:
        public = ScriptedMain(MainDecision(intent="inspect", entry_id="market_rule"))
        secret = ScriptedMain(MainDecision(intent="inspect", entry_id="dockhand_card"))

        first = await self.session(public).run_turn("game", "有哪些时间线？", "turn-1")
        second = await self.session(secret).run_turn("game", "A 心里怎么想？", "turn-2")

        self.assertEqual(second.snapshot.tick, 0)
        self.assertIn("旧码头", first.narration)
        self.assertNotIn("只知道亲眼见过", second.narration)
        self.assertEqual(len(self.store.player_inputs_for("game")), 2)

    async def test_committed_turn_survives_narration_failure(self) -> None:
        class FailingNarrator(ScriptedMain):
            async def summarize(self, player_text: str, visible_results: list[str]) -> str:
                raise RuntimeError("narrator unavailable")

        main = FailingNarrator(MainDecision(intent="action", action_id="break_shop_window"))

        outcome = await self.session(main).run_turn("game", "我打破橱窗", "turn-1")

        self.assertTrue(outcome.narration_fallback)
        self.assertIn("碎玻璃", outcome.narration)
        self.assertEqual(outcome.snapshot.tick, 1)


if __name__ == "__main__":
    unittest.main()
