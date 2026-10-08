"""Exercise the default story call through the installed AgentScope 2 SDK."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

from openai.types.chat import ChatCompletion

from story_harness.adapters.model_config import NpcModelConfig
from story_harness.adapters.store import SQLiteGameStore
from story_harness.agents.scene_turn import SceneContextProjector, SingleSceneGenerator
from story_harness.core.billing import collect_usage
from story_harness.world.scenario import ScenarioPackage


def test_single_call_structured_reply_records_v2_cached_usage():
    asyncio.run(_run_single_call_structured_reply())


async def _run_single_call_structured_reply():
    package = ScenarioPackage.load(Path(__file__).resolve().parents[1] / "examples" / "freeform")
    with tempfile.TemporaryDirectory() as directory:
        store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
        package.seed_game(store, "game")
        model = NpcModelConfig("test-model", "test-key", "https://example.invalid/v1",
                               task="single_scene", tool_choice_policy="auto_only").create_model()
        model.client.chat.completions.create = AsyncMock(return_value=ChatCompletion.model_validate({
            "id": "test-completion", "created": 0, "model": "test-model",
            "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [{
                    "id": "structured-1", "type": "function", "function": {
                        "name": "generate_structured_output",
                        "arguments": '{"prose":"你听见船靠岸。"}',
                    },
                }],
            }}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10,
                      "prompt_tokens_details": {"cached_tokens": 2}},
        }))
        context = SceneContextProjector(store, package).project(store.load("game"), "早上好")

        with collect_usage() as usage:
            turn = await SingleSceneGenerator(model, package).generate("game", context)

        assert turn.prose == "你听见船靠岸。"
        assert model.client.chat.completions.create.await_count == 1
        assert model.client.chat.completions.create.await_args.kwargs["tool_choice"] == "auto"
        assert usage.records[0].cached_input_tokens == 2
        assert usage.records[0].task == "single_scene"
