import asyncio
import json
import unittest

from agentscope_fakes import ChatModelBase, ChatResponse

from story_harness.core.contracts import PendingWork, Snapshot
from story_harness.agents.selector_agent import AgentScopeWorkSelector


class ChoiceModel(ChatModelBase):
    def __init__(self, selected_id: str) -> None:
        super().__init__(model_name="selector-test", stream=False)
        self.selected_id = selected_id
        self.prompts: list[object] = []

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        self.prompts.append(prompt)
        return ChatResponse(content=[{"type": "text", "text": "选择已提交"}],
                            metadata={"work_id": self.selected_id})


class AgentScopeWorkSelectorTests(unittest.TestCase):
    def test_react_agent_selects_only_from_visible_candidate_summaries(self) -> None:
        model = ChoiceModel("b")
        selector = AgentScopeWorkSelector(model, max_iters=3)
        snapshot = Snapshot("game-1", 4, 8, {"secret": "幕后真相"})
        options = [
            PendingWork("a", "npc_plan", 8, 1, None, {"summary": "A 去图书馆", "secret": "凶手是 A"}, False),
            PendingWork("b", "scene", 8, 1, None, {"summary": "窗户旁传来响声"}, False),
        ]

        selected = asyncio.run(selector(snapshot, options))

        self.assertEqual(selected.work_id, "b")
        first_prompt = json.dumps(model.prompts[0], ensure_ascii=False)
        self.assertIn("窗户旁传来响声", first_prompt)
        self.assertNotIn("凶手是 A", first_prompt)
        self.assertNotIn("幕后真相", first_prompt)

    def test_invalid_choice_is_rejected(self) -> None:
        model = ChoiceModel("unknown")
        selector = AgentScopeWorkSelector(model, max_iters=3)
        snapshot = Snapshot("game-1", 0, 0, {})
        options = [PendingWork("a", "scene", 0, 1, None, {"summary": "场景 A"}, False)]

        with self.assertRaises(ValueError):
            asyncio.run(selector(snapshot, options))


if __name__ == "__main__":
    unittest.main()
