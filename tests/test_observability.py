import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agentscope.model import ChatModelBase, ChatResponse, OpenAIChatModel
from agentscope.model._model_usage import ChatUsage

from story_harness.adapters.model_config import CompatibleOpenAIChatModel
from story_harness.adapters.store import SQLiteGameStore
from story_harness.adapters.telemetry import LangfuseTelemetry, configured_telemetry, observed_tool
from story_harness.agents.main_agent import MainDecision, MainReActAgent
from story_harness.cli.interaction_demo import run_interaction_demo
from story_harness.runtime.game_session import GameSession
from story_harness.world.scenario import ScenarioPackage


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "freeform"


class FakeObservation:
    def __init__(self, calls):
        self.calls = calls

    def update(self, **kwargs):
        self.calls.append(("update", kwargs))

    def score_trace(self, **kwargs):
        self.calls.append(("score", kwargs))


class FakeContext:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return FakeObservation(self.calls)

    def __exit__(self, *args):
        self.calls.append(("exit", args[0]))


class FakeLangfuse:
    def __init__(self):
        self.calls = []

    def start_as_current_observation(self, **kwargs):
        self.calls.append(("start", kwargs))
        return FakeContext(self.calls)


class ScriptedMain:
    async def decide(self, text):
        return MainDecision(intent="inspect", entry_id="missing")

    async def summarize(self, text, results):
        return "\n".join(results)


class SceneDecisionModel(ChatModelBase):
    def __init__(self):
        super().__init__(model_name="scene-test", stream=False)
        self.calls = 0

    async def __call__(self, messages, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return ChatResponse(content=[{
                "type": "tool_use", "id": "scene-1", "name": "get_scene",
                "input": {}, "raw_input": "{}",
            }])
        return ChatResponse(content=[{
            "type": "tool_use", "id": "decision-1", "name": "generate_response",
            "input": {"intent": "inspect", "target_ids": [], "channel": "speech", "entry_id": None},
            "raw_input": '{"intent":"inspect"}',
        }])


class ObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_offline_demo_uses_the_same_observability_adapter(self):
        client = FakeLangfuse()

        await run_interaction_demo(EXAMPLE, turns=1, telemetry=LangfuseTelemetry(client))

        names = [value["name"] for kind, value in client.calls if kind == "start"]
        self.assertIn("game-turn", names)
        self.assertIn("work:npc_reply", names)
        self.assertIn("npc-response", names)
        self.assertTrue(any(kind == "score" and value["name"] == "story.work_processed"
                            for kind, value in client.calls))

    async def test_incomplete_langfuse_credentials_are_reported(self):
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "public", "LANGFUSE_SECRET_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY"):
                configured_telemetry()

    async def test_main_context_and_world_tool_are_visible_as_separate_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage.load(EXAMPLE)
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            client = FakeLangfuse()
            agent = MainReActAgent(
                "game", store, package.worldbook, SceneDecisionModel(),
                telemetry=LangfuseTelemetry(client),
            )

            decision = await agent.decide("看看周围")

            self.assertEqual(decision.intent, "inspect")
            starts = [value for kind, value in client.calls if kind == "start"]
            context = next(item for item in starts if item["name"] == "main-context")
            self.assertEqual(context["metadata"]["sources"], [
                "current_state", "recent_player_inputs", "recent_player_observations",
            ])
            tool = next(item for item in starts if item["name"] == "tool:get_scene")
            self.assertEqual(tool["as_type"], "tool")

    async def test_session_trace_covers_decision_work_and_narration_with_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage.load(EXAMPLE)
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            client = FakeLangfuse()
            session = GameSession(
                store, package, lambda _: ScriptedMain(), npc_pool=None,
                max_steps=2, telemetry=LangfuseTelemetry(client),
            )

            result = await session.run_turn("game", "查看档案", "turn-123")

            starts = [value for kind, value in client.calls if kind == "start"]
            self.assertEqual(starts[0]["name"], "story-turn")
            self.assertEqual(starts[0]["metadata"]["turn_id"], "turn-123")
            self.assertEqual([item["name"] for item in starts[1:3]], ["main-decision", "work-queue"])
            self.assertIn("main-narration", [item["name"] for item in starts])
            self.assertTrue(any(
                value.get("metadata", {}).get("processed_work_count") == len(result.processed_work_ids)
                for kind, value in client.calls if kind == "update"
            ))
            self.assertTrue(any(
                value.get("metadata", {}).get("narration_fallback") is False
                for kind, value in client.calls if kind == "update"
            ))
            scores = {value["name"]: value["value"] for kind, value in client.calls if kind == "score"}
            self.assertEqual(scores, {
                "story.work_processed": float(len(result.processed_work_ids)),
                "story.work_remaining": float(len(store.pending_work("game"))),
                "story.player_observations": float(len(result.player_observations)),
                "story.narration_fallback": 0.0,
                "story.turn_success": 1.0,
            })

    async def test_game_trace_reports_failure_without_changing_exception(self):
        class BrokenMain:
            async def decide(self, text):
                raise ValueError("decision unavailable")

        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage.load(EXAMPLE)
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            client = FakeLangfuse()
            session = GameSession(store, package, lambda _: BrokenMain(), None, 1,
                                  telemetry=LangfuseTelemetry(client))

            with self.assertRaisesRegex(ValueError, "decision unavailable"):
                await session.run_turn("game", "hi", "broken")

            self.assertTrue(any(kind == "exit" and value is ValueError for kind, value in client.calls))
            self.assertTrue(any(
                kind == "score" and value["name"] == "story.turn_success" and value["value"] == 0.0
                for kind, value in client.calls
            ))

    async def test_model_generation_reports_model_usage_and_omits_content_by_default(self):
        client = FakeLangfuse()
        model = CompatibleOpenAIChatModel(
            model_name="test-model", api_key="never-log-this", stream=False,
            telemetry=LangfuseTelemetry(client), task="main_react",
        )
        response = ChatResponse(
            content=[{"type": "text", "text": "secret reply"}],
            usage=ChatUsage(input_tokens=7, output_tokens=3, time=0.1),
        )
        with patch.object(OpenAIChatModel, "__call__", new=AsyncMock(return_value=response)):
            await model([{"role": "user", "content": "secret prompt"}])

        starts = [value for kind, value in client.calls if kind == "start"]
        self.assertEqual(starts[0]["as_type"], "generation")
        self.assertEqual(starts[0]["model"], "test-model")
        self.assertEqual(starts[0]["metadata"]["task"], "main_react")
        updates = [value for kind, value in client.calls if kind == "update"]
        self.assertIn({"usage_details": {"input": 7, "output": 3}}, updates)
        self.assertNotIn("secret prompt", repr(client.calls))
        self.assertNotIn("secret reply", repr(client.calls))
        self.assertNotIn("never-log-this", repr(client.calls))

    async def test_content_capture_and_tool_spans_are_explicit_opt_in(self):
        client = FakeLangfuse()
        telemetry = LangfuseTelemetry(client, capture_content=True)

        def get_scene(location: str):
            return {"location": location, "nearby": ["A"]}

        result = observed_tool(get_scene, telemetry)("private room")

        self.assertEqual(result["nearby"], ["A"])
        start = next(value for kind, value in client.calls if kind == "start")
        self.assertEqual(start["as_type"], "tool")
        self.assertEqual(start["input"], {"location": "private room"})
        self.assertIn("nearby", repr(client.calls))


if __name__ == "__main__":
    unittest.main()
