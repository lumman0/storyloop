import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from agentscope.model import ChatModelBase, ChatResponse

from story_harness.core.contracts import Snapshot
from story_harness.agents.main_agent import MainReActAgent
from story_harness.runtime.player_input import submit_player_input
from story_harness.adapters.store import SQLiteGameStore
from story_harness.world.worldbook import Worldbook


class ToolThenPlanModel(ChatModelBase):
    def __init__(self) -> None:
        super().__init__(model_name="main-test", stream=False)
        self.prompts: list[object] = []

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            request = {"entry_id": "public_rule"}
            return ChatResponse(content=[{
                "type": "tool_use", "id": "read-1", "name": "get_worldbook_entry",
                "input": request, "raw_input": json.dumps(request),
            }])
        decision = {"intent": "speech", "target_ids": ["A"], "channel": "speech", "entry_id": None, "action_id": None}
        return ChatResponse(content=[{
            "type": "tool_use", "id": "plan-1", "name": "generate_response",
            "input": decision, "raw_input": json.dumps(decision),
        }])


class MainAgentTests(unittest.TestCase):
    def test_main_react_can_use_worldbook_tool_without_private_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book_path = root / "worldbook.json"
            book_path.write_text(json.dumps({
                "package_id": "sample", "version": "1",
                "entries": [
                    {"id": "public_rule", "kind": "rule", "text": "大厅可以交谈", "visibility": "public"},
                    {"id": "private_truth", "kind": "truth", "text": "A 是凶手", "visibility": "secret"},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            store = SQLiteGameStore(str(root / "game.sqlite3"))
            store.create_game(Snapshot("game", 0, 0, {
                "actors": {"player": {"location": "hall"}, "A": {"location": "hall"}},
                "secret": "A 是凶手",
            }))
            model = ToolThenPlanModel()
            agent = MainReActAgent("game", store, Worldbook.load(book_path), model, max_iters=4)

            decision = asyncio.run(agent.decide("和 A 聊聊"))

            self.assertEqual(decision.intent, "speech")
            self.assertEqual(decision.target_ids, ["A"])
            prompt = json.dumps(model.prompts, ensure_ascii=False)
            self.assertIn("大厅可以交谈", prompt)
            self.assertNotIn("A 是凶手", prompt)

    def test_new_main_agent_reads_persisted_player_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book_path = root / "worldbook.json"
            book_path.write_text(json.dumps({
                "package_id": "sample", "version": "1", "entries": [],
            }), encoding="utf-8")
            store = SQLiteGameStore(str(root / "game.sqlite3"))
            store.create_game(Snapshot("game", 0, 0, {
                "actors": {"player": {"location": "hall"}, "A": {"location": "hall"}},
            }))
            submit_player_input(store, "game", "old-input", "我之前找过 A", ("A",))
            model = ToolThenPlanModel()
            agent = MainReActAgent("game", store, Worldbook.load(book_path), model)

            asyncio.run(agent.decide("继续聊"))

            self.assertIn("我之前找过 A", json.dumps(model.prompts, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
