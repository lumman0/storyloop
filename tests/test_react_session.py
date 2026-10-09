import json
import tempfile
import unittest
from pathlib import Path

from agentscope_fakes import ChatModelBase, ChatResponse

from storyloop_platform.legacy.npc_agent import NpcAgentPool
from storyloop_platform.runtime.game_session import GameSession
from storyloop_platform.legacy.main_agent import MainReActAgent
from storyloop_harness.world.scenario import ScenarioPackage
from storyloop_platform.adapters.store import SQLiteGameStore


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "freeform"


class ActionModel(ChatModelBase):
    def __init__(self) -> None:
        super().__init__(model_name="action-test", stream=False)
        self.calls = 0
        self.prompts: list[object] = []

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.calls += 1
        self.prompts.append(prompt)
        if self.calls == 1:
            return ChatResponse(content=[{
                "type": "tool_use", "id": "actions-1", "name": "get_available_actions",
                "input": {}, "raw_input": "{}",
            }])
        decision = {
            "intent": "action", "target_ids": [], "channel": "speech",
            "entry_id": None, "action_id": "break_shop_window",
        }
        return ChatResponse(content=[{
            "type": "tool_use", "id": "decision-1", "name": "generate_response",
            "input": decision, "raw_input": json.dumps(decision),
        }])


class NarrationModel(ChatModelBase):
    def __init__(self) -> None:
        super().__init__(model_name="narration-test", stream=False)
        self.prompts: list[object] = []

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.prompts.append(prompt)
        narration = {"text": "橱窗碎了。"}
        return ChatResponse(content=[{
            "type": "tool_use", "id": "narration-1", "name": "generate_response",
            "input": narration, "raw_input": json.dumps(narration, ensure_ascii=False),
        }])


class SpeechModel(ChatModelBase):
    def __init__(self) -> None:
        super().__init__(model_name="speech-test", stream=False)
        self.calls = 0
        self.prompts: list[object] = []

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.calls += 1
        self.prompts.append(prompt)
        if self.calls == 1:
            return ChatResponse(content=[{
                "type": "tool_use", "id": "scene-1", "name": "get_scene",
                "input": {}, "raw_input": "{}",
            }])
        decision = {
            "intent": "speech", "target_ids": ["dockhand"], "channel": "speech",
            "entry_id": None, "action_id": None,
        }
        return ChatResponse(content=[{
            "type": "tool_use", "id": "speech-1", "name": "generate_response",
            "input": decision, "raw_input": json.dumps(decision),
        }])


class NpcModel(ChatModelBase):
    def __init__(self) -> None:
        super().__init__(model_name="npc-test", stream=False)

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        return ChatResponse(content=[{"type": "text", "text": "A：你好。"}])


class ReactSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_main_react_tool_action_commit_and_narration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage.load(EXAMPLE)
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            action_model = ActionModel()
            narration_model = NarrationModel()
            main_created = []
            main_agents = []

            def main_factory(game_id: str) -> MainReActAgent:
                main_created.append(game_id)
                main = MainReActAgent(
                    game_id, store, package.worldbook, action_model,
                    action_rules=package.action_rules, narration_model=narration_model,
                    opening=package.opening,
                )
                main_agents.append(main)
                return main

            session = GameSession(
                store, package, main_factory,
                NpcAgentPool(store, lambda _game, _actor: ActionModel()),
                max_steps=8,
            )
            result = await session.run_turn("game", "我打破橱窗", "turn-1")

            self.assertEqual(result.narration, "橱窗碎了。")
            self.assertTrue(result.snapshot.data["world"]["shop_window"]["broken"])
            self.assertEqual([item.text for item in store.player_inputs_for("game")], ["我打破橱窗"])
            self.assertIn("break_shop_window", json.dumps(action_model.prompts, ensure_ascii=False))
            self.assertIn("你来到港口广场", json.dumps(action_model.prompts, ensure_ascii=False))
            self.assertEqual(main_created, ["game"])
            self.assertEqual(await main_agents[0].agent.memory.get_memory(), [])
            self.assertEqual(await main_agents[0].narrator.memory.get_memory(), [])
            self.assertIn("碎玻璃", json.dumps(narration_model.prompts, ensure_ascii=False))

    async def test_main_react_selects_npc_and_commits_independent_reply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage.load(EXAMPLE)
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            speech_model = SpeechModel()
            narration_model = NarrationModel()
            session = GameSession(
                store,
                package,
                lambda game_id: MainReActAgent(
                    game_id, store, package.worldbook, speech_model,
                    action_rules=package.action_rules, narration_model=narration_model,
                ),
                NpcAgentPool(store, lambda _game, _actor: NpcModel()),
                max_steps=8,
            )

            events = []

            async def collect(event):
                events.append(event)

            result = await session.run_turn("game", "你好，A", "turn-1", progress=collect)

            self.assertEqual(result.decision.target_ids, ["dockhand"])
            self.assertEqual(result.snapshot.tick, 1)
            self.assertIn("【码头工】\nA：你好。", [item.content for item in result.player_observations])
            self.assertIn("dockhand", json.dumps(speech_model.prompts, ensure_ascii=False))
            self.assertEqual(result.narration, "【码头工】\nA：你好。")
            self.assertEqual(narration_model.prompts, [])
            self.assertEqual([item["stage"] for item in events if item["type"] == "stage"],
                             ["thinking", "committing", "characters", "narrating"])
            self.assertTrue(any(item["type"] == "segment" and item["segment"]["kind"] == "dialogue"
                                for item in events))


if __name__ == "__main__":
    unittest.main()
