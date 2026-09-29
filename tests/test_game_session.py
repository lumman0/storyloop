import tempfile
import unittest
from pathlib import Path

from agentscope.model import ChatModelBase, ChatResponse

from story_harness.agents.npc_agent import NpcAgentPool
from story_harness.runtime.game_session import GameSession, compose_visible_narration
from story_harness.core.contracts import Observation
from story_harness.agents.main_agent import MainDecision
from story_harness.world.scenario import ScenarioPackage
from story_harness.adapters.store import SQLiteGameStore
from story_harness.runtime.schedule import advance_time


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
        self.assertEqual(outcome.narration, "A：我听见了。")
        self.assertEqual(main.visible_results, [])

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
