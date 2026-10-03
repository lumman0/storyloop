import tempfile
import unittest
from pathlib import Path

from agentscope.model import ChatModelBase, ChatResponse

from story_harness.adapters.store import SQLiteGameStore
from story_harness.agents.action_resolver import ModelActionResolver
from story_harness.world.scenario import ScenarioPackage


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "freeform"


class ResolutionModel(ChatModelBase):
    def __init__(self):
        super().__init__(model_name="resolution-test", stream=False)
        self.prompt = None

    async def __call__(self, prompt, **kwargs):
        self.prompt = prompt
        return ChatResponse(content=[{"type": "text", "text": ""}], metadata={
            "status": "occurred",
            "player_result": "你抬手拍了对方一下。",
            "sensory": "玩家抬手拍了码头工一下。",
            "target_ids": ["dockhand"],
            "effects": [],
        })


class ActionResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_open_action_without_scripted_verb(self):
        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage.load(EXAMPLE)
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            model = ResolutionModel()

            outcome = await ModelActionResolver(store, package, model).resolve(
                store.load("game"), "拍一下码头工", ("dockhand",),
            )

            self.assertEqual(outcome.status, "occurred")
            self.assertEqual(outcome.target_ids, ("dockhand",))
            self.assertIn("码头工", outcome.sensory)
            self.assertIsNotNone(model.prompt)
