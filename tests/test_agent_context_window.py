"""Focused regression checks for per-save agent context compaction."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from agentscope_fakes import ChatModelBase, ChatResponse

from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_platform.legacy.main_agent import MainReActAgent
from storyloop_platform.legacy.npc_agent import NpcAgentPool
from storyloop_harness.core.contracts import Snapshot, WorldEvent
from storyloop_harness.runtime.player_input import submit_player_input
from storyloop_harness.world.worldbook import Worldbook


class DecisionModel(ChatModelBase):
    def __init__(self) -> None:
        super().__init__(model_name="decision-test", stream=False)
        self.prompts: list[object] = []

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.prompts.append(prompt)
        decision = {"intent": "speech", "target_ids": [], "channel": "speech"}
        return ChatResponse(content=[{
            "type": "tool_use", "id": "done", "name": "generate_response",
            "input": decision, "raw_input": json.dumps(decision),
        }])


class ReplyModel(ChatModelBase):
    def __init__(self) -> None:
        super().__init__(model_name="reply-test", stream=False)
        self.prompts: list[object] = []

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.prompts.append(prompt)
        return ChatResponse(content=[{"type": "text", "text": "我记得之前的事。"}])


class SummaryModel(ChatModelBase):
    def __init__(self) -> None:
        super().__init__(model_name="summary-test", stream=False)
        self.prompts: list[object] = []

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.prompts.append(prompt)
        return ChatResponse(content=[{"type": "text", "text": "已压缩"}],
                            metadata={"summary": "较早的对话已确认：玩家重视诚实。"})


class AgentContextWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = SQLiteGameStore(str(root / "game.sqlite3"))
        self.store.create_game(Snapshot("save-a", 0, 0, {
            "actors": {"player": {"location": "hall"}, "A": {"location": "hall"}},
        }))
        worldbook = root / "worldbook.json"
        worldbook.write_text('{"package_id":"test","version":"1","entries":[]}', encoding="utf-8")
        self.worldbook = Worldbook.load(worldbook)

    def test_main_keeps_full_history_until_budget_then_persists_summary(self) -> None:
        summary_model = SummaryModel()
        submit_player_input(self.store, "save-a", "short", "我喜欢诚实", ())
        first = DecisionModel()
        asyncio.run(MainReActAgent(
            "save-a", self.store, self.worldbook, first,
            context_window_tokens=3000, compression_model=summary_model,
        ).decide("继续"))
        self.assertEqual(len(summary_model.prompts), 0)
        self.assertIn("我喜欢诚实", json.dumps(first.prompts, ensure_ascii=False))

        for index in range(14):
            submit_player_input(self.store, "save-a", f"long-{index}",
                                f"第 {index} 次谈话：" + "冬夜里慢慢认识彼此。" * 12, ())
        second = DecisionModel()
        asyncio.run(MainReActAgent(
            "save-a", self.store, self.worldbook, second,
            context_window_tokens=3000, compression_model=summary_model,
        ).decide("继续"))
        self.assertGreater(len(summary_model.prompts), 0)
        self.assertIn("较早的对话已确认", json.dumps(second.prompts, ensure_ascii=False))
        self.assertIn("第 13 次谈话", json.dumps(second.prompts, ensure_ascii=False))

        restarted = SQLiteGameStore(self.store.path)
        third = DecisionModel()
        calls = len(summary_model.prompts)
        asyncio.run(MainReActAgent(
            "save-a", restarted, self.worldbook, third,
            context_window_tokens=3000, compression_model=summary_model,
        ).decide("再聊聊"))
        self.assertEqual(len(summary_model.prompts), calls)
        self.assertIn("较早的对话已确认", json.dumps(third.prompts, ensure_ascii=False))

    def test_npc_context_is_bounded_and_isolated_after_pool_restart(self) -> None:
        for index in range(12):
            before = self.store.load("save-a")
            self.store.commit("save-a", before.version, WorldEvent(
                f"a-{index}", "npc_spoke", "A", None, before.tick, (),
                {"player_message": "玩家问起" + str(index),
                 "speech": "A 的旧回答：" + "雪下得很安静。" * 15},
            ), (), ())
        summary_model = SummaryModel()
        first = ReplyModel()
        pool = NpcAgentPool(
            self.store, lambda _game, _actor: first,
            context_window_tokens=3000, compression_model=summary_model,
        )
        asyncio.run(pool.respond("save-a", "A", "谨慎的嘉宾", "今天怎么样？"))
        prompt = json.dumps(first.prompts, ensure_ascii=False)
        self.assertGreater(len(summary_model.prompts), 0)
        self.assertIn("较早的对话已确认", prompt)
        self.assertIn("玩家问起11", prompt)
        other = ReplyModel()
        other_pool = NpcAgentPool(
            self.store, lambda _game, _actor: other,
            context_window_tokens=3000, compression_model=summary_model,
        )
        asyncio.run(other_pool.respond("save-a", "B", "刚到场的嘉宾", "你好"))
        self.assertNotIn("较早的对话已确认", json.dumps(other.prompts, ensure_ascii=False))

        restarted = SQLiteGameStore(self.store.path)
        second = ReplyModel()
        calls = len(summary_model.prompts)
        pool = NpcAgentPool(
            restarted, lambda _game, _actor: second,
            context_window_tokens=3000, compression_model=summary_model,
        )
        asyncio.run(pool.respond("save-a", "A", "谨慎的嘉宾", "再聊聊"))
        self.assertEqual(len(summary_model.prompts), calls)
        self.assertIn("较早的对话已确认", json.dumps(second.prompts, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
