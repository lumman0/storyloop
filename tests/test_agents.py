import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from agentscope.model import ChatModelBase, ChatResponse

from story_harness.agents.npc_agent import NpcAgentPool
from story_harness.core.contracts import Effect, Observation, PendingWork, Snapshot, WorldEvent
from story_harness.runtime.npc_work import make_npc_reply_handler
from story_harness.runtime.runner import TurnRunner
from story_harness.adapters.store import SQLiteGameStore
from story_harness.world.worldbook import Worldbook


class RecordingModel(ChatModelBase):
    def __init__(self, name: str) -> None:
        super().__init__(model_name=name, stream=False)
        self.prompts: list[object] = []

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.prompts.append(prompt)
        return ChatResponse(content=[{"type": "text", "text": f"reply from {self.model_name}"}])


class FailOnceModel(RecordingModel):
    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            raise RuntimeError("temporary model failure")
        return ChatResponse(content=[{"type": "text", "text": "recovered"}])


class SlowRecordingModel(RecordingModel):
    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.prompts.append(prompt)
        await asyncio.sleep(0.02)
        return ChatResponse(content=[{"type": "text", "text": "slow reply"}])


class NpcToolModel(RecordingModel):
    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.prompts.append(prompt)
        if len(self.prompts) <= 2:
            entry_id = "b_secret" if len(self.prompts) == 1 else "a_card"
            request = {"entry_id": entry_id}
            return ChatResponse(content=[{
                "type": "tool_use", "id": f"read-{len(self.prompts)}",
                "name": "get_known_worldbook_entry", "input": request,
                "raw_input": json.dumps(request),
            }])
        return ChatResponse(content=[{"type": "text", "text": "我只说我知道的。"}])


class NpcAgentPoolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteGameStore(str(Path(self.temp.name) / "agents.sqlite3"))
        self.store.create_game(Snapshot("game-1", 0, 0, {"world": {}}))
        event = WorldEvent("heard-secrets", "conversation", None, None, 0, ())
        observations = (
            Observation("for-a", event.event_id, "A", "heard", "A 独有线索", 0),
            Observation("for-b", event.event_id, "B", "heard", "B 独有线索", 0),
        )
        self.store.commit("game-1", 0, event, observations, ())
        self.models: dict[tuple[str, str], RecordingModel] = {}

        def model_factory(game_id: str, actor_id: str) -> RecordingModel:
            model = RecordingModel(f"{game_id}:{actor_id}")
            self.models[(game_id, actor_id)] = model
            return model

        self.pool = NpcAgentPool(self.store, model_factory, max_iters=2)

    async def test_each_npc_receives_only_own_observations(self) -> None:
        a_reply = await self.pool.respond("game-1", "A", "谨慎的目击者", "发生了什么？")
        b_reply = await self.pool.respond("game-1", "B", "善于打听消息", "你知道什么？")

        a_prompt = json.dumps(self.models[("game-1", "A")].prompts, ensure_ascii=False)
        b_prompt = json.dumps(self.models[("game-1", "B")].prompts, ensure_ascii=False)
        self.assertIn("A 独有线索", a_prompt)
        self.assertNotIn("B 独有线索", a_prompt)
        self.assertIn("B 独有线索", b_prompt)
        self.assertNotIn("A 独有线索", b_prompt)
        self.assertIn("reply from game-1:A", a_reply)
        self.assertIn("reply from game-1:B", b_reply)

    async def test_npc_worldbook_tool_respects_actor_visibility(self) -> None:
        path = Path(self.temp.name) / "worldbook.json"
        path.write_text(json.dumps({
            "package_id": "sample", "version": "1", "entries": [
                {"id": "a_card", "text": "A 知道一枚银币", "visibility": "actor", "allowed_actors": ["A"]},
                {"id": "b_secret", "text": "B 私藏一把钥匙", "visibility": "actor", "allowed_actors": ["B"]},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        model = NpcToolModel("A-tools")
        pool = NpcAgentPool(
            self.store, lambda _game, _actor: model,
            max_iters=4, worldbook=Worldbook.load(path),
        )

        reply = await pool.respond("game-1", "A", "谨慎的目击者", "你知道什么？")

        prompt = json.dumps(model.prompts, ensure_ascii=False)
        self.assertEqual(reply, "我只说我知道的。")
        self.assertIn("A 知道一枚银币", prompt)
        self.assertNotIn("B 私藏一把钥匙", prompt)

    async def test_same_npc_keeps_its_memory_without_reinjecting_old_observations(self) -> None:
        await self.pool.respond("game-1", "A", "谨慎的目击者", "第一次")
        await self.pool.respond("game-1", "A", "谨慎的目击者", "第二次")

        model = self.models[("game-1", "A")]
        self.assertEqual(len(model.prompts), 2)
        second_prompt = json.dumps(model.prompts[1], ensure_ascii=False)
        self.assertIn("第一次", second_prompt)
        self.assertIn("第二次", second_prompt)
        self.assertEqual(second_prompt.count("A 独有线索"), 1)

    async def test_failed_model_call_does_not_duplicate_observation_on_retry(self) -> None:
        model = FailOnceModel("game-1:A")
        pool = NpcAgentPool(self.store, lambda game_id, actor_id: model, max_iters=2)

        with self.assertRaises(RuntimeError):
            await pool.respond("game-1", "A", "谨慎的目击者", "第一次")
        reply = await pool.respond("game-1", "A", "谨慎的目击者", "重试")

        self.assertEqual(reply, "recovered")
        second_prompt = json.dumps(model.prompts[1], ensure_ascii=False)
        self.assertEqual(second_prompt.count("A 独有线索"), 1)

    async def test_concurrent_calls_to_same_npc_do_not_duplicate_delivery(self) -> None:
        model = SlowRecordingModel("game-1:A")
        pool = NpcAgentPool(self.store, lambda game_id, actor_id: model, max_iters=2)

        await asyncio.gather(
            pool.respond("game-1", "A", "谨慎的目击者", "问题一"),
            pool.respond("game-1", "A", "谨慎的目击者", "问题二"),
        )

        self.assertEqual(len(model.prompts), 2)
        second_prompt = json.dumps(model.prompts[1], ensure_ascii=False)
        self.assertEqual(second_prompt.count("A 独有线索"), 1)

    async def test_npc_reply_work_commits_a_player_visible_dialogue_event(self) -> None:
        work = PendingWork(
            "ask-a",
            "npc_reply",
            0,
            10,
            "heard-secrets",
            {"actor_id": "A", "player_message": "你看到了什么？"},
        )
        self.store.commit("game-1", 1, None, (), (work,))
        handler = make_npc_reply_handler(self.pool, {"A": "谨慎的目击者"})

        result = await TurnRunner(self.store, {"npc_reply": handler}, max_steps=1).run_async("game-1")

        self.assertEqual(result.processed_work_ids, ("ask-a",))
        self.assertEqual(result.snapshot.version, 2)
        player_observations = self.store.observations_for("game-1", "player")
        self.assertEqual(len(player_observations), 1)
        self.assertEqual(player_observations[0].channel, "dialogue")
        self.assertIn("reply from game-1:A", player_observations[0].content)

    async def test_campaign_npc_reply_cannot_advance_past_choice_gate(self) -> None:
        self.store.create_game(Snapshot("campaign-game", 0, 0, {
            "scenario": {"id": "show"}, "campaign": {"cursor": 0}, "actors": {"A": {}},
        }), (PendingWork("slow-reply", "npc_reply", 0, 10, None, {
            "actor_id": "A", "player_message": "你好", "duration_ticks": 2,
        }),))
        handler = make_npc_reply_handler(self.pool, {"A": "嘉宾"})

        with self.assertRaisesRegex(ValueError, "campaign.*duration_ticks"):
            await TurnRunner(self.store, {"npc_reply": handler}, 1).run_async("campaign-game")
        self.assertEqual(self.store.load("campaign-game").tick, 0)
        self.assertEqual(len(self.store.pending_work("campaign-game")), 1)

    async def test_failed_world_commit_rolls_back_uncommitted_npc_memory(self) -> None:
        work = PendingWork(
            "ask-a",
            "npc_reply",
            0,
            10,
            "heard-secrets",
            {"actor_id": "A", "player_message": "你看到了什么？"},
        )
        self.store.commit("game-1", 1, None, (), (work,))
        handler = make_npc_reply_handler(self.pool, {"A": "谨慎的目击者"})

        class RejectingStore:
            def __init__(self, actual: SQLiteGameStore) -> None:
                self.actual = actual

            def load(self, game_id: str) -> Snapshot:
                return self.actual.load(game_id)

            def ready_work(self, game_id: str, tick: int) -> list[PendingWork]:
                return self.actual.ready_work(game_id, tick)

            def commit(self, *args: object, **kwargs: object) -> Snapshot:
                raise ValueError("simulated version conflict")

        with self.assertRaises(ValueError):
            await TurnRunner(RejectingStore(self.store), {"npc_reply": handler}, 1).run_async("game-1")

        self.assertEqual(len(self.store.pending_work("game-1")), 1)
        self.assertEqual(self.store.observations_for("game-1", "player"), [])
        result = await asyncio.wait_for(
            TurnRunner(self.store, {"npc_reply": handler}, 1).run_async("game-1"),
            timeout=2,
        )
        self.assertEqual(result.snapshot.version, 2)
        second_prompt = json.dumps(self.models[("game-1", "A")].prompts[1], ensure_ascii=False)
        self.assertEqual(second_prompt.count("A 独有线索"), 1)
        self.assertEqual(second_prompt.count("你看到了什么？"), 1)
        self.assertNotIn("reply from game-1:A", second_prompt)

    async def test_new_agent_pool_recovers_its_own_committed_dialogue(self) -> None:
        work = PendingWork(
            "ask-a",
            "npc_reply",
            0,
            10,
            "heard-secrets",
            {"actor_id": "A", "player_message": "旧问题"},
        )
        self.store.commit("game-1", 1, None, (), (work,))
        handler = make_npc_reply_handler(self.pool, {"A": "谨慎的目击者"})
        await TurnRunner(self.store, {"npc_reply": handler}, 1).run_async("game-1")

        model = RecordingModel("new-process:A")
        restarted_pool = NpcAgentPool(
            SQLiteGameStore(self.store.path),
            lambda game_id, actor_id: model,
            max_iters=2,
        )
        await restarted_pool.respond("game-1", "A", "谨慎的目击者", "新问题")

        prompt = json.dumps(model.prompts[0], ensure_ascii=False)
        self.assertIn("旧问题", prompt)
        self.assertIn("reply from game-1:A", prompt)
        self.assertNotIn("B 独有线索", prompt)

    async def test_talking_advances_time_and_releases_due_background_work(self) -> None:
        self.store.create_game(
            Snapshot("game-2", 0, 0, {"plot": {"pressure": 0}}),
            (
                PendingWork(
                    "ask-a-2", "npc_reply", 0, 10, None,
                    {"actor_id": "A", "player_message": "聊聊天"},
                ),
                PendingWork("background", "advance_plot", 1, 5, None, {}),
            ),
        )

        def advance_plot(snapshot: Snapshot, work: PendingWork):
            from story_harness.runtime.runner import WorkResult

            event = WorldEvent(
                "plot-advanced", "plot_pressure", None, work.work_id,
                snapshot.tick, (Effect(("plot", "pressure"), 1),),
            )
            return WorkResult(event, (), ())

        handlers = {
            "npc_reply": make_npc_reply_handler(self.pool, {"A": "谨慎的目击者"}),
            "advance_plot": advance_plot,
        }

        result = await TurnRunner(self.store, handlers, 2).run_async("game-2")

        self.assertEqual(result.processed_work_ids, ("ask-a-2", "background"))
        self.assertEqual(result.snapshot.tick, 1)
        self.assertEqual(result.snapshot.data["plot"]["pressure"], 1)


if __name__ == "__main__":
    unittest.main()
