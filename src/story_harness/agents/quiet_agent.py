"""AgentScope ReAct agent whose internal steps stay out of the game CLI."""

from __future__ import annotations

from agentscope.agent import ReActAgent
from agentscope.message import AudioBlock, Msg


class QuietReActAgent(ReActAgent):
    async def print(
        self,
        msg: Msg,
        last: bool = True,
        speech: AudioBlock | list[AudioBlock] | None = None,
    ) -> None:
        return None
