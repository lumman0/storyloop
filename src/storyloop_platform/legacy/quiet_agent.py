"""Game-scoped AgentScope 2 agent with a short-lived working context."""

from __future__ import annotations

from agentscope.agent import Agent, ReActConfig
from agentscope.message import Msg
from agentscope.model import ChatModelBase
from agentscope.tool import Toolkit


class _WorkingMemory:
    def __init__(self, agent: "QuietReActAgent") -> None:
        self.agent = agent

    async def clear(self) -> None:
        self.agent.state.context.clear()
        self.agent.state.summary = ""

    async def get_memory(self) -> list[Msg]:
        return list(self.agent.state.context)


class QuietReActAgent(Agent):
    def __init__(self, *, name: str, sys_prompt: str, model: ChatModelBase,
                 formatter: object, toolkit: Toolkit, memory: object,
                 max_iters: int) -> None:
        super().__init__(
            name=name, system_prompt=sys_prompt, model=model, toolkit=toolkit,
            react_config=ReActConfig(
                max_iters=max_iters, structured_output_grace_iters=1,
                interruption_raise_cancelled_error=True,
            ),
        )
        self.sys_prompt = sys_prompt
        self.formatter = formatter
        self.memory = _WorkingMemory(self)

    async def __call__(self, message: Msg, *, structured_model: type | None = None) -> Msg:
        response = await self.reply(message, structured_schema=structured_model)
        if structured_model is not None:
            response.metadata = response.structured_output or {}
        return response

    def state_dict(self) -> dict:
        return self.state.model_dump(mode="python")

    def load_state_dict(self, state: dict) -> None:
        self.state = type(self.state).model_validate(state)
