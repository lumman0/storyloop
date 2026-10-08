"""Write all eligible campaign messages in one model call."""

from __future__ import annotations

import json
from dataclasses import dataclass

from story_harness.adapters.agentscope_message import Msg
from agentscope.model import ChatModelBase
from pydantic import BaseModel, Field

from story_harness.adapters.store import GameStore
from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry, session_id_for_game
from story_harness.agents.openai_formatter import ThinkingSafeOpenAIChatFormatter
from story_harness.world.scenario import ScenarioPackage


class MessageDraft(BaseModel):
    actor_id: str
    text: str = Field(min_length=1)


class MessageSceneDraft(BaseModel):
    prose: str = Field(min_length=1)
    messages: list[MessageDraft] = Field(default_factory=list)


@dataclass(frozen=True)
class MessageScene:
    prose: str
    messages: dict[str, str]


class SingleCallMessageWriter:
    """One shared generation, with input histories still scoped per sender."""

    def __init__(self, store: GameStore, package: ScenarioPackage,
                 model: ChatModelBase, telemetry: Telemetry | None = None) -> None:
        self.store = store
        self.package = package
        self.model = model
        self.telemetry = telemetry or LangfuseTelemetry()
        self.formatter = ThinkingSafeOpenAIChatFormatter()

    async def write(self, game_id: str, senders: tuple[str, ...], recipient: str | None,
                    player_note: str, fallback: dict[str, str]) -> MessageScene:
        snapshot = self.store.load(game_id)
        campaign = snapshot.data.get("campaign", {})
        day = campaign.get("day") if isinstance(campaign, dict) else None
        player_history = [item.content[:250] for item in
                          self.store.agent_context_entries(game_id, "player")[-6:]]
        contexts = []
        for actor_id in senders:
            if actor_id not in self.package.role_cards:
                continue
            checkpoint = self.store.agent_context_checkpoint(game_id, actor_id)
            history = self.store.agent_context_entries(game_id, actor_id,
                                                       checkpoint.through_version)
            contexts.append({
                "id": actor_id, "name": self.package.actor_names[actor_id],
                "role_card": self.package.role_cards[actor_id][:1100],
                "own_summary": checkpoint.summary[:800],
                "own_history": [item.content[:300] for item in history[-8:]],
                "player_note_to_this_actor": player_note if actor_id == recipient else None,
            })
        request = {"day": day, "recipient": recipient,
                   "recent_player_visible_events": player_history,
                   "senders": contexts,
                   "fallback_messages": fallback}
        system = (
            "你是恋爱节目消息场景的单次主控。一次写出所有 sender 的心动留言和一小段第二人称场景正文。"
            "每个 sender 只能依据自己的 role_card、own_summary、own_history 写话；"
            "只有 recipient 能看见 player_note_to_this_actor，不要把它告诉其他人。"
            "不要让某位角色知道另一位角色的私人经历或消息。"
            "messages 中每位 sender 恰好一条 20 至 70 字的自然留言，避免同文案；"
            "prose 描写玩家发出留言或等待消息的片刻，不替玩家增加心理、动作和决定。"
            "不需要在 prose 中重复消息全文，消息会单独显示。"
            "fallback_messages 仅用于理解剧本语气，不要逐字复制。只输出结构化结果。"
        )
        prompt = await self.formatter.format(msgs=[
            Msg("system", system, "system"),
            Msg("player", json.dumps(request, ensure_ascii=False), "user"),
        ])
        with self.telemetry.span(
            "single-message-generation", {"game_id": game_id, "sender_ids": list(senders)},
            kind="agent", input=request if self.telemetry.capture_content else None,
            session_id=session_id_for_game(game_id, self.package.package_id),
        ) as span:
            response = await self.model(prompt, structured_model=MessageSceneDraft)
            draft = MessageSceneDraft.model_validate(response.metadata)
            messages = {}
            for item in draft.messages:
                candidate = " ".join(item.text.strip().strip('“”"').split())
                if item.actor_id in senders and item.actor_id not in messages and 1 <= len(candidate) <= 140:
                    messages[item.actor_id] = candidate
            span.metric("story.single_message_model_calls", 1.0)
            if self.telemetry.capture_content:
                span.update(output=draft.model_dump())
            return MessageScene(draft.prose.strip().replace("\\n", "\n"), messages)
