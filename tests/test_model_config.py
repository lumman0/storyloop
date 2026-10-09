import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agentscope.model import OpenAIChatModel
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from model_helpers import create_test_model
from storyloop_platform.config import load_settings, default_settings, ModelFactory
from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_harness.agents.scene_turn import SingleSceneGenerator, SceneContextProjector
from test_single_call import a_turn
from storyloop_platform.portal.billing import collect_usage
from storyloop_harness.world.scenario import ScenarioPackage


class ModelFactoryTests(unittest.TestCase):
    def test_model_timeouts_and_missing_credentials(self):
        settings = default_settings()
        with self.assertRaisesRegex(ValueError, 'STORY_MODEL_API_KEY'):
            ModelFactory(settings, env={}).create_model('single_turn')
        model = ModelFactory(settings, env={'STORY_MODEL_API_KEY': 'test-token'}).create_model('single_turn')
        self.assertEqual(model.client.timeout.connect, 10)
        self.assertEqual(model.client.timeout.read, 90)
        self.assertEqual(model.client.max_retries, 2)


class ReplySchema(BaseModel):
    text: str


class MissingUsageTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_response_without_usage_cannot_be_collected(self) -> None:
        model = create_test_model("test-model", "test-key")
        response = SimpleNamespace(content="hello", usage=None)
        with patch.object(OpenAIChatModel, "__call__", new_callable=AsyncMock,
                          return_value=response):
            with collect_usage() as usage:
                with self.assertRaisesRegex(RuntimeError, "model did not report token usage"):
                    await model([{"role": "user", "content": "hello"}])
                self.assertEqual(usage.records, [])

    async def test_structured_response_without_usage_cannot_be_collected(self) -> None:
        model = create_test_model("test-model", "test-key")
        response = SimpleNamespace(content={"text": "hello"}, usage=None)
        with patch.object(OpenAIChatModel, "generate_structured_output", new_callable=AsyncMock,
                          return_value=response):
            with collect_usage() as usage:
                with self.assertRaisesRegex(RuntimeError, "model did not report token usage"):
                    await model([{"role": "user", "content": "hello"}],
                                structured_model=ReplySchema)
                self.assertEqual(usage.records, [])

    async def test_missing_usage_is_allowed_without_collection(self) -> None:
        model = create_test_model("test-model", "test-key")
        response = SimpleNamespace(content="hello", usage=None)
        with patch.object(OpenAIChatModel, "__call__", new_callable=AsyncMock,
                          return_value=response):
            self.assertIs(await model([{"role": "user", "content": "hello"}]), response)
        structured = SimpleNamespace(content={"text": "hello"}, usage=None)
        with patch.object(OpenAIChatModel, "generate_structured_output", new_callable=AsyncMock,
                          return_value=structured):
            result = await model([{"role": "user", "content": "hello"}],
                                 structured_model=ReplySchema)
            self.assertEqual(result.metadata, structured.content)


class ToolChoiceCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_only_policy_converts_forced_tool_choice(self) -> None:
        model = create_test_model(
            "qwen3.8-max", "test-token", "https://example.invalid/v1",
            tool_choice_policy="auto_only",
        )
        with patch.object(OpenAIChatModel, "__call__", new_callable=AsyncMock) as call:
            await model([{"role": "user", "content": "hello"}], tools=[{"type": "function"}], tool_choice="required")

        self.assertEqual(call.await_args.kwargs["tool_choice"].mode, "auto")

    async def test_native_policy_preserves_forced_tool_choice(self) -> None:
        model = create_test_model(
            "other-model", "test-token", "https://example.invalid/v1",
            tool_choice_policy="native",
        )
        with patch.object(OpenAIChatModel, "__call__", new_callable=AsyncMock) as call:
            await model([{"role": "user", "content": "hello"}], tools=[{"type": "function"}], tool_choice="required")

        self.assertEqual(call.await_args.kwargs["tool_choice"].mode, "required")

    async def test_single_turn_sends_auto_to_qwen_compatible_endpoint(self) -> None:
        root = Path(__file__).resolve().parents[1]
        package = ScenarioPackage.load(root / "examples" / "freeform")
        config = load_settings(root / "config" / "local.json")
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            model = ModelFactory(config, env={"STORY_MODEL_API_KEY": "test-token"}).create_model("single_turn")
            decision = {**a_turn(), "participants": ["dockhand"]}
            choices: list[str | None] = []

            async def completion(**kwargs: object) -> ChatCompletion:
                choice = kwargs.get("tool_choice")
                choices.append(choice if isinstance(choice, str) else None)
                tool_names = [item.get("function", {}).get("name")
                              for item in kwargs.get("tools", [])]
                message = (
                    {"role": "assistant", "content": "我会和码头工打招呼。"}
                    if choice != "auto" or "generate_structured_output" not in tool_names else
                    {"role": "assistant", "content": None, "tool_calls": [{
                        "id": "decision-1", "type": "function", "function": {
                            "name": "generate_structured_output", "arguments": json.dumps(decision),
                        },
                    }]}
                )
                return ChatCompletion.model_validate({
                    "id": "chatcmpl-test", "created": 0, "model": "qwen3.8-max",
                    "object": "chat.completion", "choices": [{
                        "finish_reason": "tool_calls" if choice == "auto" and "generate_structured_output" in tool_names else "stop",
                        "index": 0, "message": message,
                    }],
                })

            model.client.chat.completions.create = AsyncMock(side_effect=completion)
            generator = SingleSceneGenerator(model, package)
            result = await generator.generate("game", SceneContextProjector(store, package).project(store.load("game"), "hi"))

            self.assertEqual(result.decision.target_ids, ["dockhand"])
            self.assertIn("auto", choices)
            self.assertNotIn("required", choices)


if __name__ == "__main__":
    unittest.main()
