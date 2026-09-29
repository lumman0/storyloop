"""Format model history without replaying provider-only thinking blocks."""

from __future__ import annotations

from copy import copy
from typing import Any

from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg


class ThinkingSafeOpenAIChatFormatter(OpenAIChatFormatter):
    """Keep AgentScope's OpenAI format while omitting unsupported thinking."""

    async def _format(self, msgs: list[Msg]) -> list[dict[str, Any]]:
        cleaned: list[Msg] = []
        for msg in msgs:
            if isinstance(msg.content, list) and any(
                block.get("type") == "thinking" for block in msg.content
            ):
                clone = copy(msg)
                clone.content = [
                    block for block in msg.content if block.get("type") != "thinking"
                ]
                cleaned.append(clone)
            else:
                cleaned.append(msg)
        return await super()._format(cleaned)
