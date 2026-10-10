import tempfile
import unittest
import os
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agentscope.model import OpenAIChatModel
from agentscope.credential import OpenAICredential
from agentscope_fakes import ChatModelBase, ChatResponse
from agentscope.model._model_usage import ChatUsage

from storyloop_harness.generation import CompatibleOpenAIChatModel
from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_platform.adapters.telemetry import LangfuseTelemetry, configured_telemetry, observed_tool
from storyloop_harness.world.scenario import ScenarioPackage
from storyloop_harness.agents.scene_turn import SceneContextProjector
from storyloop_harness.runtime.single_call import SingleCallGameSession
from test_single_call import FakeGenerator, a_turn


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


class ObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_turns_share_game_session_across_root_and_child_observations(self):
        active_session = ContextVar("test_langfuse_session", default=None)
        sessions_seen: list[tuple[str, str | None]] = []
        observations_per_turn = []

        @contextmanager
        def propagate_attributes(*, session_id: str):
            token = active_session.set(session_id)
            try:
                yield
            finally:
                active_session.reset(token)

        class SessionClient(FakeLangfuse):
            def start_as_current_observation(self, **kwargs):
                sessions_seen.append((kwargs["name"], active_session.get()))
                return super().start_as_current_observation(**kwargs)

        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage.load(EXAMPLE)
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            client = SessionClient()
            session = SingleCallGameSession(
                store, package, FakeGenerator(a_turn()), SceneContextProjector(store, package),
                max_steps=2, telemetry=LangfuseTelemetry(client),
            )
            fake_langfuse = SimpleNamespace(propagate_attributes=propagate_attributes)
            with patch.dict(sys.modules, {"langfuse": fake_langfuse}):
                package.seed_game(store, "港口-1")
                for game_id, text, turn_id in (
                    ("game", "查看周围", "turn-1"),
                    ("game", "再看一次", "turn-2"),
                    ("港口-1", "查看周围", "turn-3"),
                ):
                    start = len(sessions_seen)
                    await session.run_turn(game_id, text, turn_id)
                    observations_per_turn.append(sessions_seen[start:])

        root_sessions = [session_id for name, session_id in sessions_seen if name == "single-call-turn"]
        self.assertEqual(root_sessions[:2], ["harbor-freeform:game"] * 2)
        self.assertEqual(len(root_sessions), 3)
        self.assertTrue(root_sessions[2].isascii())
        self.assertNotEqual(root_sessions[2], "harbor-freeform:game")
        self.assertEqual(root_sessions[2], "game-" +
                         sha256("harbor-freeform:港口-1".encode("utf-8")).hexdigest())
        for expected_session, observations in zip(root_sessions, observations_per_turn):
            for name in ("single-call-turn", "game-turn", "work:single_npc_reply"):
                self.assertEqual([session_id for observed_name, session_id in observations
                                  if observed_name == name], [expected_session])
            self.assertTrue(all(session_id == expected_session
                                for _, session_id in observations))
        self.assertTrue(all(session_id is not None for _, session_id in sessions_seen))
        self.assertIsNone(active_session.get())

    async def test_incomplete_langfuse_credentials_are_reported(self):
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "public", "LANGFUSE_SECRET_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY"):
                configured_telemetry()

    async def test_scene_trace_records_generation_and_failure_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            package = ScenarioPackage.load(EXAMPLE)
            store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
            package.seed_game(store, "game")
            client = FakeLangfuse()
            generator = FakeGenerator(a_turn())
            session = SingleCallGameSession(store, package, generator,
                SceneContextProjector(store, package), telemetry=LangfuseTelemetry(client))
            result = await session.run_turn("game", "hello", "one")
            names = [value["name"] for kind, value in client.calls if kind == "start"]
            self.assertIn("single-call-turn", names)
            self.assertIn("work:single_npc_reply", names)
            self.assertEqual(result.processed_work_ids, ("one:input:reply:dockhand",))
            self.assertEqual([work.work_id for work in store.pending_work("game")],
                             ["harbor-opening-cue"])
            scores = {value["name"]: value["value"]
                      for kind, value in client.calls if kind == "score"}
            self.assertEqual(scores, {
                "story.turn_model_calls": 1.0,
                "story.work_processed": float(len(result.processed_work_ids)),
                "story.work_remaining": float(len(store.pending_work("game"))),
            })
            before = store.load("game")
            async def fail(*args):
                raise ValueError("scene unavailable")
            generator.generate = fail
            with self.assertRaisesRegex(ValueError, "scene unavailable"):
                await session.run_turn("game", "again", "two")
            self.assertEqual(store.load("game"), before)
            self.assertTrue(any(kind == "exit" and value is ValueError for kind, value in client.calls))

    async def test_model_generation_reports_model_usage_and_omits_content_by_default(self):
        client = FakeLangfuse()
        model = CompatibleOpenAIChatModel(
            credential=OpenAICredential(api_key="never-log-this"),
            model="test-model", stream=False,
            telemetry=LangfuseTelemetry(client), task="single_turn",
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
        self.assertEqual(starts[0]["metadata"]["task"], "single_turn")
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
