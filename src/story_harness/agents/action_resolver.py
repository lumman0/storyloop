"""Adjudicate open player actions from player-visible context."""

from __future__ import annotations

import json
from typing import Literal

from story_harness.adapters.agentscope_message import Msg
from agentscope.model import ChatModelBase
from pydantic import BaseModel, Field

from story_harness.adapters.store import GameStore
from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry
from story_harness.agents.openai_formatter import ThinkingSafeOpenAIChatFormatter
from story_harness.core.contracts import Effect, Snapshot
from story_harness.core.open_actions import OpenActionOutcome, _read_path
from story_harness.world.scenario import ScenarioPackage


class ProposedEffect(BaseModel):
    path: list[str]
    value: str | int | bool


class ActionResolution(BaseModel):
    status: Literal["occurred", "attempted", "blocked"]
    player_result: str = Field(min_length=1)
    sensory: str = Field(min_length=1)
    target_ids: list[str] = Field(default_factory=list)
    effects: list[ProposedEffect] = Field(default_factory=list)


class ModelActionResolver:
    """Propose an outcome; GameSession validates actors and every durable effect."""

    def __init__(self, store: GameStore, package: ScenarioPackage, model: ChatModelBase,
                 telemetry: Telemetry | None = None) -> None:
        self.store = store
        self.package = package
        self.model = model
        self.telemetry = telemetry or LangfuseTelemetry()
        self.formatter = ThinkingSafeOpenAIChatFormatter()

    async def resolve(self, before: Snapshot, player_text: str,
                      suggested_targets: tuple[str, ...]) -> OpenActionOutcome:
        actors = before.data.get("actors", {})
        player = actors.get("player", {}) if isinstance(actors, dict) else {}
        location = player.get("location") if isinstance(player, dict) else None
        nearby = {
            actor_id: self.package.actor_names.get(actor_id, actor_id)
            for actor_id, state in actors.items()
            if actor_id != "player" and isinstance(state, dict)
            and state.get("location") == location
        } if isinstance(actors, dict) else {}
        request = {
            "player_action": player_text,
            "location": location,
            "nearby_people": nearby,
            "suggested_target_ids": [actor_id for actor_id in suggested_targets if actor_id in nearby],
            "recent_visible_events": [
                {"channel": item.channel, "content": item.content[:500]}
                for item in self.store.observations_for(before.game_id, "player")[-6:]
            ],
            "public_setting": [entry.text[:700]
                               for entry in self.package.worldbook.visible_lore("player", limit=3)],
            "mutable_state": [
                {"path": list(field.path), "current": _read_path(before.data, field.path),
                 "allowed_values": list(field.values)}
                for field in self.package.mutable_fields
            ],
        }
        system = (
            "你是互动故事的行动裁决器。玩家可以尝试任何行动，不需要预设动词清单。"
            "只根据当前可见情境判断动作发生、被阻止或只是尝试；不能凭空添加人物、物品、规则或秘密。"
            "player_result 用简短中文描写实际结果，不要仅重复玩家输入，也不要替 NPC 说台词。"
            "sensory 用第三人称写出在场者可感知的事实，不能把未成功的动作写成已完成。"
            "target_ids 只能从 nearby_people 选择需要立即回应的相关人物。"
            "只有 mutable_state 列出的字段能产生持久 effects，value 必须是该字段允许的值。"
            "需要改变已跟踪的物品或位置时必须给出相应 effect；不要修改未列出的状态。"
            "动作未发生时 effects 必须为空。只输出符合 ActionResolution 的结构化结果。"
        )
        prompt = await self.formatter.format(msgs=[
            Msg("system", system, "system"),
            Msg("player", json.dumps(request, ensure_ascii=False), "user"),
        ])
        with self.telemetry.span(
            "open-action-resolution",
            {"game_id": before.game_id, "tick": before.tick,
             "nearby_actor_ids": list(nearby), "mutable_field_count": len(self.package.mutable_fields)},
            kind="agent", input=request if self.telemetry.capture_content else None,
        ) as span:
            response = await self.model(prompt, structured_model=ActionResolution)
            resolved = ActionResolution.model_validate(response.metadata)
            if any(actor_id not in nearby for actor_id in resolved.target_ids):
                raise ValueError("action resolver selected a person outside the current scene")
            outcome = OpenActionOutcome(
                resolved.status, resolved.player_result.strip(), resolved.sensory.strip(),
                tuple(dict.fromkeys(resolved.target_ids or request["suggested_target_ids"])),
                tuple(Effect(tuple(effect.path), effect.value) for effect in resolved.effects),
            )
            span.update(metadata={"outcome": outcome.status,
                                  "target_ids": outcome.target_ids,
                                  "effect_paths": [".".join(item.path) for item in outcome.effects]})
            if self.telemetry.capture_content:
                span.update(output=resolved.model_dump())
            return outcome
