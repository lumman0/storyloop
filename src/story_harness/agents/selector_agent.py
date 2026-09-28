"""Constrained AgentScope ReAct selection among discretionary work."""

from __future__ import annotations

import json

from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model import ChatModelBase
from agentscope.tool import Toolkit
from pydantic import BaseModel, Field

from story_harness.core.contracts import PendingWork, Snapshot
from story_harness.agents.quiet_agent import QuietReActAgent


class WorkChoice(BaseModel):
    work_id: str = Field(description="The ID of one offered work item")


class AgentScopeWorkSelector:
    """Select a queued candidate without seeing hidden state or raw payloads."""

    def __init__(self, model: ChatModelBase, max_iters: int = 3) -> None:
        self.model = model
        self.max_iters = max_iters

    async def __call__(
        self, snapshot: Snapshot, options: list[PendingWork]
    ) -> PendingWork:
        if not options:
            raise ValueError("cannot select from an empty work list")
        agent = QuietReActAgent(
            name="main-selector",
            sys_prompt=(
                "你是游戏主控 ReAct 的待办选择部分。"
                "只从提供的候选 ID 中选一项，考虑当前时间和剧情相关性。"
                "你不能修改世界状态，也不能假定未提供的幕后事实。"
            ),
            model=self.model,
            formatter=OpenAIChatFormatter(),
            toolkit=Toolkit(),
            memory=InMemoryMemory(),
            max_iters=self.max_iters,
        )
        visible_options = [
            {
                "work_id": item.work_id,
                "kind": item.kind,
                "due_tick": item.due_tick,
                "priority": item.priority,
                "summary": item.payload.get("summary", ""),
            }
            for item in options
        ]
        request = json.dumps(
            {
                "game_id": snapshot.game_id,
                "state_version": snapshot.version,
                "tick": snapshot.tick,
                "options": visible_options,
            },
            ensure_ascii=False,
        )
        response = await agent(
            Msg("scheduler", request, "user"), structured_model=WorkChoice
        )
        if not isinstance(response.metadata, dict):
            raise ValueError("selector returned no structured choice")
        chosen_id = WorkChoice.model_validate(response.metadata).work_id
        for item in options:
            if item.work_id == chosen_id:
                return item
        raise ValueError("selector chose work outside the ready queue")
