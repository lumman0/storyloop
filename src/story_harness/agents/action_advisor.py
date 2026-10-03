"""Optional player actions based only on the final visible story."""

from __future__ import annotations

import asyncio
import json
import re

from agentscope.message import Msg
from agentscope.model import ChatModelBase
from pydantic import BaseModel, Field

from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry, session_id_for_game
from story_harness.agents.openai_formatter import ThinkingSafeOpenAIChatFormatter


class ActionOption(BaseModel):
    label: str = Field(min_length=2, max_length=50)
    input: str = Field(min_length=2, max_length=500)


class ThreeActions(BaseModel):
    options: list[ActionOption]


class ActionOptionAdvisor:
    """One cheap model call per ordinary visible result; never changes world state."""

    def __init__(self, model: ChatModelBase, telemetry: Telemetry | None = None,
                 timeout_seconds: float = 12) -> None:
        self.model = model
        self.telemetry = telemetry or LangfuseTelemetry()
        self.formatter = ThinkingSafeOpenAIChatFormatter()
        self.timeout_seconds = timeout_seconds

    async def suggest(self, visible_text: str, presentation_mode: str,
                      game_id: str = "", scenario_id: str = "",
                      story_context: dict | None = None,
                      recent_actions: tuple[str, ...] = ()) -> tuple[ActionOption, ...]:
        story_context = story_context or {}
        authored_leads = tuple(ActionOption.model_validate(item)
                               for item in story_context.get("leads", []))
        used_actions = {action.strip() for action in recent_actions}
        anchors = tuple(str(item).strip() for item in story_context.get("anchors", [])
                        if isinstance(item, str) and item.strip())
        request = {"presentation_mode": presentation_mode,
                   "visible_story": visible_text[-3500:],
                   "current_scene": story_context.get("scene", ""),
                   "current_goal": story_context.get("goal", ""),
                   "story_anchors": anchors,
                   "authored_leads": [lead.model_dump() for lead in authored_leads],
                   "recent_player_actions": list(recent_actions[-4:])}
        system = (
            "你为文游玩家提供恰好三个可直接执行的下一步行动。只依据玩家已经看见的故事，"
            "不要使用隐藏设定、猜测幕后真相、编造NPC或物品。优先围绕 current_goal 与"
            "authored_leads，让每条行动触及当前已出现的人物或事件，并能带来新对话、"
            "新信息或关系变化；不能只是坐下、观察、继续探索，也不能重复 recent_player_actions。"
            "三个行动方向应不同；每个 label 是具体的简短按钮文字，input 是点击后原样提交的"
            "玩家行动句子。input 用第一人称“我”表达玩家意图，不代替 NPC 发言，"
            "不得包含 /choose、/next、/rest 等系统命令，不要跳过玩家决策。"
            "选项只是建议，玩家仍可自由输入。仅输出 ThreeActions 结构化结果。"
        )
        candidates: tuple[ActionOption, ...] = ()
        try:
            prompt = await self.formatter.format(msgs=[
                Msg("system", system, "system"),
                Msg("player", json.dumps(request, ensure_ascii=False), "user"),
            ])
            with self.telemetry.span("followup-action-model",
                                     {"presentation_mode": presentation_mode},
                                     kind="agent",
                                     input=request if self.telemetry.capture_content else None,
                                     session_id=session_id_for_game(game_id, scenario_id)
                                     if game_id else None) as span:
                response = await asyncio.wait_for(
                    self.model(prompt, structured_model=ThreeActions), self.timeout_seconds,
                )
                options = tuple(ThreeActions.model_validate(response.metadata).options)
                candidates = options
                labels = {option.label.strip() for option in options}
                actions = {option.input.strip() for option in options}
                blank = any(not option.label.strip() or not option.input.strip()
                            for option in options)
                command = any(
                    re.search(r"/(?:choose|next|rest)\b", option.input + option.label, re.I)
                    for option in options
                )
                ungrounded = bool(anchors) and any(
                    not any(anchor in option.label + option.input for anchor in anchors)
                    for option in options
                )
                repeated = any(option.input.strip() in used_actions for option in options)
                if (len(options) != 3 or len(labels) != 3 or len(actions) != 3
                        or blank or command or ungrounded or repeated):
                    raise ValueError("invalid or duplicate follow-up actions")
                span.metric("story.followup_actions", 3.0)
                if self.telemetry.capture_content:
                    span.update(output=[option.model_dump() for option in options])
                return options
        except Exception as error:
            with self.telemetry.span("followup-action-fallback",
                                     {"error_type": type(error).__name__},
                                     session_id=session_id_for_game(game_id, scenario_id)
                                     if game_id else None) as span:
                span.metric("story.followup_action_fallback", 1.0)
            fallback = authored_leads or (
                ActionOption(label="观察周围", input="我观察一下周围的环境和在场的人。"),
                ActionOption(label="整理线索", input="我整理一下刚才亲眼看到和亲耳听到的事。"),
                ActionOption(label="继续探索", input="我在当前所在的地方继续探索。"),
            )
            # A scene can last several turns. Its authored leads are a pool of
            # suggestions, not a menu to replay after a failed model call.
            selected: list[ActionOption] = []
            for option in (*candidates, *fallback):
                if (not option.input.strip() or not option.label.strip()
                    or option.input.strip() in used_actions
                    or any(existing.input == option.input or existing.label == option.label
                           for existing in selected)
                    or re.search(r"/(?:choose|next|rest)\b", option.input + option.label, re.I)
                    or (anchors and not any(anchor in option.input + option.label for anchor in anchors))):
                    continue
                selected.append(option)
                if len(selected) == 3:
                    break
            return tuple(selected)
