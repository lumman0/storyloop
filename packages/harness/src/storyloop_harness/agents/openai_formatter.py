"""Format model history without replaying provider-only thinking blocks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg, ThinkingBlock


class ThinkingSafeOpenAIChatFormatter(OpenAIChatFormatter):
    """Keep AgentScope's OpenAI format while omitting unsupported thinking."""

    async def format(self, msgs: list[Msg]) -> list[dict[str, Any]]:
        cleaned: list[Msg] = []
        for msg in msgs:
            if any(isinstance(block, ThinkingBlock) for block in msg.content):
                clone = deepcopy(msg)
                clone.content = [block for block in msg.content
                                 if not isinstance(block, ThinkingBlock)]
                cleaned.append(clone)
            else:
                cleaned.append(msg)
        return await super().format(cleaned)
