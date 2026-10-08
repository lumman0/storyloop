"""Bound and persist an agent's view of committed game history.

The source events and observations are never deleted. Only their prompt projection
is compressed, independently for the player-facing main agent and each NPC.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from story_harness.adapters.agentscope_message import Msg
from agentscope.model import ChatModelBase
from pydantic import BaseModel, Field

from story_harness.adapters.store import GameStore
from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry
from story_harness.core.contracts import AgentContextCheckpoint, AgentContextEntry
from story_harness.agents.openai_formatter import ThinkingSafeOpenAIChatFormatter


class ContextSummary(BaseModel):
    summary: str = Field(min_length=1, max_length=1600)


class ContextCompressor(Protocol):
    async def compress(self, actor_id: str, previous: str,
                       entries: tuple[AgentContextEntry, ...]) -> str: ...


class ModelContextCompressor:
    """Use a separately routed model to summarize only actor-visible facts."""

    def __init__(self, model: ChatModelBase) -> None:
        self.model = model
        self.formatter = ThinkingSafeOpenAIChatFormatter()

    async def compress(self, actor_id: str, previous: str,
                       entries: tuple[AgentContextEntry, ...]) -> str:
        perspective = ("玩家已知" if actor_id == "player" else f"角色 {actor_id} 亲历或获知")
        prompt = await self.formatter.format(msgs=[
            Msg("system", (
                "你负责压缩互动故事的历史上下文。只保留输入中明确出现、之后可能影响互动的"
                "人物关系、承诺、线索、已知事件和未解决的问题。保留谁知道什么及不确定性，"
                "不要把猜测写成事实，不要创造新剧情或泄露其他角色的秘密。"
                "以第三人称写简明中文摘要，最多 600 字。"
            ), "system"),
            Msg("history", json.dumps({
                "perspective": perspective,
                "previous_summary": previous,
                "committed_history": [
                    {"channel": entry.channel, "text": entry.content, "tick": entry.tick}
                    for entry in entries
                ],
            }, ensure_ascii=False), "user"),
        ])
        response = await self.model(prompt, structured_model=ContextSummary)
        if not isinstance(response.metadata, dict):
            raise ValueError("context compression returned no structured summary")
        return ContextSummary.model_validate(response.metadata).summary.strip()


@dataclass(frozen=True)
class AgentContextView:
    summary: str
    recent: tuple[AgentContextEntry, ...]
    through_version: int
    estimated_tokens: int
    compressed_entries: int


def estimate_tokens(text: str) -> int:
    """Conservative, provider-independent text estimate; includes UTF-8 cost."""
    return max(len(text), (len(text.encode("utf-8")) + 1) // 2)


class AgentContextManager:
    """Compress a committed prefix only when a prompt approaches its budget."""

    def __init__(self, store: GameStore, compressor: ContextCompressor,
                 context_window_tokens: int = 65536,
                 telemetry: Telemetry | None = None) -> None:
        if type(context_window_tokens) is not int or context_window_tokens < 1024:
            raise ValueError("context_window_tokens must be at least 1024")
        self.store = store
        self.compressor = compressor
        self.context_window_tokens = context_window_tokens
        # Tool results, ReAct steps and completion need room after the first prompt.
        self.input_budget = context_window_tokens - max(
            256, min(65536, context_window_tokens // 4),
        )
        self.telemetry = telemetry or LangfuseTelemetry()

    @staticmethod
    def _render(summary: str, entries: list[AgentContextEntry]) -> str:
        return json.dumps({
            "summary": summary,
            "history": [
                {"channel": item.channel, "text": item.content, "tick": item.tick}
                for item in entries
            ],
        }, ensure_ascii=False)

    async def prepare(self, game_id: str, actor_id: str, *,
                      fixed_context: str = "", incoming: str = "") -> AgentContextView:
        checkpoint = self.store.agent_context_checkpoint(game_id, actor_id)
        recent = self.store.agent_context_entries(
            game_id, actor_id, after_version=checkpoint.through_version,
        )
        base_size = estimate_tokens(fixed_context + incoming)
        compressed_entries = 0

        def projected_size() -> int:
            return base_size + estimate_tokens(self._render(checkpoint.summary, recent))

        while recent and projected_size() > self.input_budget:
            # Keep the two newest committed events verbatim whenever possible.
            distinct_versions = list(dict.fromkeys(item.state_version for item in recent))
            eligible = (distinct_versions[:-2] if len(distinct_versions) > 2
                        else distinct_versions[:1])
            if not eligible:
                break
            max_chunk = max(256, self.input_budget // 2)
            cutoff = eligible[0]
            for version in eligible:
                candidate = [item for item in recent if item.state_version <= version]
                if (estimate_tokens(self._render(checkpoint.summary, candidate))
                        > max_chunk and version != eligible[0]):
                    break
                cutoff = version
            chunk = tuple(item for item in recent if item.state_version <= cutoff)
            with self.telemetry.span("agent-context-compression", {
                "game_id": game_id, "actor_id": actor_id,
                "previous_through_version": checkpoint.through_version,
                "through_version": cutoff,
                "entry_count": len(chunk),
            }, kind="agent") as span:
                summary = await self.compressor.compress(actor_id, checkpoint.summary, chunk)
                if not summary or estimate_tokens(summary) > self.input_budget // 2:
                    raise ValueError("context compression produced an oversized or empty summary")
                new_checkpoint = AgentContextCheckpoint(cutoff, summary)
                self.store.save_agent_context_checkpoint(
                    game_id, actor_id, checkpoint.through_version, new_checkpoint,
                )
                span.metric("story.context_compressed_entries", float(len(chunk)))
                span.metric("story.context_summary_estimated_tokens", float(estimate_tokens(summary)))
            checkpoint = new_checkpoint
            compressed_entries += len(chunk)
            recent = [item for item in recent if item.state_version > cutoff]

        if projected_size() > self.input_budget:
            raise ValueError("agent context exceeds configured window even after compression")
        return AgentContextView(checkpoint.summary, tuple(recent),
                                checkpoint.through_version, projected_size(),
                                compressed_entries)
