import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agentscope.model import OpenAIChatModel
from openai.types.chat import ChatCompletion

from story_harness.adapters.model_config import BailianModelRouter, NpcModelConfig
from story_harness.adapters.runtime_config import HarnessConfig
from story_harness.adapters.store import SQLiteGameStore
from story_harness.agents.main_agent import MainReActAgent
from story_harness.world.scenario import ScenarioPackage


class NpcModelConfigTests(unittest.TestCase):
    def test_bailian_token_plan_routes_light_and_deep_tasks(self) -> None:
        router = BailianModelRouter.from_environment({"STORY_BAILIAN_API_KEY": "test-token"})

        light = router.create_model("npc_selection")
        deep = router.create_model("npc_reply")

        self.assertEqual(light.model_name, "qwen3.8-flash")
        self.assertEqual(deep.model_name, "qwen3.8-max")
        self.assertEqual(str(light.client.base_url), "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/")
        self.assertNotIn("test-token", repr(router))

    def test_openai_compatible_endpoint_is_configured_without_a_network_call(self) -> None:
        config = NpcModelConfig.from_environment({
            "STORY_NPC_MODEL": "cheap-model",
            "STORY_NPC_BASE_URL": "https://example.invalid/v1",
            "STORY_NPC_API_KEY": "test-token",
        })

        model = config.create_model()

        self.assertEqual(model.model_name, "cheap-model")
        self.assertEqual(str(model.client.base_url), "https://example.invalid/v1/")
        self.assertFalse(model.stream)

    def test_missing_model_or_key_is_reported_before_play(self) -> None:
        with self.assertRaisesRegex(ValueError, "STORY_NPC_MODEL"):
            NpcModelConfig.from_environment({})
        with self.assertRaisesRegex(ValueError, "STORY_NPC_API_KEY"):
            NpcModelConfig.from_environment({"STORY_NPC_MODEL": "small"})


class ToolChoiceCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_only_policy_converts_forced_tool_choice(self) -> None:
        model = NpcModelConfig(
            "qwen3.8-max", "test-token", "https://example.invalid/v1",
            tool_choice_policy="auto_only",
        ).create_model()
        with patch.object(OpenAIChatModel, "__call__", new_callable=AsyncMock) as call:
            await model([{"role": "user", "content": "hello"}], tools=[{"type": "function"}], tool_choice="required")

        self.assertEqual(call.await_args.kwargs["tool_choice"], "auto")

    async def test_native_policy_preserves_forced_tool_choice(self) -> None:
        model = NpcModelConfig(
            "other-model", "test-token", "https://example.invalid/v1",
            tool_choice_policy="native",
        ).create_model()
        with patch.object(OpenAIChatModel, "__call__", new_callable=AsyncMock) as call:
            await model([{"role": "user", "content": "hello"}], tools=[{"type": "function"}], tool_choice="required")

        self.assertEqual(call.await_args.kwargs["tool_choice"], "required")

    async def test_main_react_sends_auto_to_qwen_compatible_endpoint(self) -> None:
        root = Path(__file__).resolve().parents[1]
        package = ScenarioPackage.load(root / "examples" / "freeform")
        config = HarnessConfig.load(root / "config" / "bailian-token-plan.json")
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            model = config.create_model("main_react", {"STORY_BAILIAN_API_KEY": "test-token"})
            decision = {
                "intent": "speech", "target_ids": ["dockhand"], "channel": "speech",
                "entry_id": None, "action_id": None,
            }
            choices: list[str | None] = []

            async def completion(**kwargs: object) -> ChatCompletion:
                choice = kwargs.get("tool_choice")
                choices.append(choice if isinstance(choice, str) else None)
                message = (
                    {"role": "assistant", "content": "我会和码头工打招呼。"}
                    if choice == "none" else
                    {"role": "assistant", "content": None, "tool_calls": [{
                        "id": "decision-1", "type": "function", "function": {
                            "name": "generate_response", "arguments": json.dumps(decision),
                        },
                    }]}
                )
                return ChatCompletion.model_validate({
                    "id": "chatcmpl-test", "created": 0, "model": "qwen3.8-max",
                    "object": "chat.completion", "choices": [{
                        "finish_reason": "stop" if choice == "none" else "tool_calls",
                        "index": 0, "message": message,
                    }],
                })

            model.client.chat.completions.create = AsyncMock(side_effect=completion)
            agent = MainReActAgent("game", store, package.worldbook, model)
            result = await agent.decide("hi")

            self.assertEqual(result.target_ids, ["dockhand"])
            self.assertEqual(choices[0], "auto")


if __name__ == "__main__":
    unittest.main()
