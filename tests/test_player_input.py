import tempfile
import unittest
from pathlib import Path

from agentscope.model import ChatModelBase, ChatResponse

from story_harness.agents.npc_agent import NpcAgentPool
from story_harness.runtime.npc_work import make_npc_reply_handler
from story_harness.runtime.player_input import submit_player_input
from story_harness.runtime.runner import TurnRunner
from story_harness.world.scenario import ScenarioPackage
from story_harness.adapters.store import SQLiteGameStore


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class PlayerInputTests(unittest.TestCase):
    def test_speech_is_recorded_and_delivered_to_only_addressed_npc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            ScenarioPackage.load(EXAMPLES / "freeform").seed_game(store, "game")

            after = submit_player_input(store, "game", "input-1", "你好，今天有什么安排？", ("dockhand",))

            self.assertEqual(after.tick, 1)
            self.assertEqual(store.player_inputs_for("game")[0].text, "你好，今天有什么安排？")
            self.assertEqual([item.content for item in store.observations_for("game", "dockhand")], ["你好，今天有什么安排？"])
            replies = [item for item in store.pending_work("game") if item.kind == "npc_reply"]
            self.assertEqual(len(replies), 1)
            self.assertEqual(replies[0].payload["duration_ticks"], 0)
            self.assertEqual(store.observations_for("game", "engineer"), [])

    def test_private_message_can_cross_locations_without_becoming_public(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            ScenarioPackage.load(EXAMPLES / "scheduled").seed_game(store, "game")

            submit_player_input(store, "game", "dm-1", "今晚聊聊？", ("engineer",), channel="private_message")

            observation = store.observations_for("game", "engineer")[0]
            self.assertEqual(observation.channel, "private_message")
            self.assertEqual(observation.content, "今晚聊聊？")
            self.assertEqual(store.observations_for("game", "player"), [])

    def test_speech_to_remote_npc_is_rejected_without_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            ScenarioPackage.load(EXAMPLES / "scheduled").seed_game(store, "game")

            with self.assertRaisesRegex(ValueError, "same location"):
                submit_player_input(store, "game", "input-1", "你好", ("engineer",))

            self.assertEqual(store.load("game").version, 0)
            self.assertEqual(store.player_inputs_for("game"), [])


if __name__ == "__main__":
    unittest.main()


class PlayerNpcIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_player_input_appears_once_in_npc_prompt(self) -> None:
        class CaptureModel(ChatModelBase):
            def __init__(self) -> None:
                super().__init__(model_name="capture", stream=False)
                self.prompts: list[object] = []

            async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
                self.prompts.append(prompt)
                return ChatResponse(content=[{"type": "text", "text": "你好，欢迎。"}])

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package = ScenarioPackage.load(EXAMPLES / "freeform")
            package.seed_game(store, "game")
            submit_player_input(store, "game", "input-1", "这家店卖什么？", ("dockhand",))
            model = CaptureModel()
            pool = NpcAgentPool(store, lambda game_id, actor_id: model)
            handler = make_npc_reply_handler(pool, package.role_cards)

            result = await TurnRunner(store, {"npc_reply": handler}, 1).run_async("game")

            self.assertEqual(result.snapshot.tick, 1)
            self.assertEqual(len(store.observations_for("game", "player")), 1)
            self.assertEqual(str(model.prompts[0]).count("这家店卖什么？"), 1)
            self.assertNotIn("港口市集每天开门一次", str(model.prompts[0]))
