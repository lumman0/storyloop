"""First-person player-visible prose from already committed story beats."""

from __future__ import annotations

import json

from agentscope.message import Msg
from agentscope.model import ChatModelBase
from pydantic import BaseModel, Field

from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry, session_id_for_game
from story_harness.agents.openai_formatter import ThinkingSafeOpenAIChatFormatter
from story_harness.runtime.presentation import SceneContext
from story_harness.runtime.player_preferences import current_player_preferences
from story_harness.world.scenario import ScenarioPackage


class NovelProse(BaseModel):
    text: str = Field(min_length=1)


class NovelTurnNarrator:
    """Compose one story passage; state changes remain exclusively with the runtime."""

    def __init__(self, package: ScenarioPackage, model: ChatModelBase,
                 telemetry: Telemetry | None = None) -> None:
        self.package = package
        self.model = model
        self.telemetry = telemetry or LangfuseTelemetry()
        self.formatter = ThinkingSafeOpenAIChatFormatter()

    async def present(self, context: SceneContext) -> str:
        beats = [
            {"kind": part.kind, "speaker": part.speaker_name, "text": part.text[:1600]}
            for part in context.segments if part.kind != "prompt" and part.text.strip()
        ]
        request = {
            "player_action": (context.player_text[:1000]
                              if not context.player_text.startswith("/") else ""),
            "day": context.day,
            "period": context.period,
            "opening": context.opening,
            "current_goal": context.current_goal[:300],
            "public_setting": [item.text[:900] for item in
                               self.package.worldbook.visible_lore("player", limit=4)],
            "scenario_opening": self.package.opening[:900] if context.opening else "",
            "visible_beats": beats[-16:],
            "player_style_preferences": list(current_player_preferences()),
        }
        system = (
            "你是文游主控的小说模式呈现器。把本轮已经发生的玩家可见结果整合为一段连贯的中文小说正文，"
            "从玩家角色第一人称“我”写出，通常约150至350字。按可见结果的发生顺序自然串起行动、环境、"
            "时间流逝和NPC回应；可依据公开设定描绘环境氛围，NPC的话可以引用，但不能新增台词或改写其事实含义。"
            "如果 visible_beats 中有 time，利用光线、环境与已经发生的事侧写时段变化；"
            "傍晚或夜深时可让叙述自然显出一天将结束，但不能替玩家决定睡觉或跳天。"
            "不要把第几天、几点或耗时提示写成独立的系统播报；这些数值由界面进度区记录。"
            "current_goal 只用于从已出现的人和事中轻轻引出下一步，不写成任务清单，"
            "也不提前透露尚未发生的节目安排。"
            "玩家行动只以 player_action 为准，不替玩家增加行为、对白、决定、感情或内心独白。"
            "不得透露未提供的秘密，不得制造新事件、人物、物品或关系；可用低风险的文学连接词。"
            "玩家画像只微调文风和节奏，不是剧情事实。不要系统提示、建议列表或第二人称叙述。"
            "没有可见事件时简短描绘停顿，不要凭空推进情节。仅输出 NovelProse 结构化结果。"
        )
        try:
            prompt = await self.formatter.format(msgs=[
                Msg("system", system, "system"),
                Msg("player", json.dumps(request, ensure_ascii=False), "user"),
            ])
            with self.telemetry.span(
                "novel-presentation-model",
                {"beat_count": len(beats), "opening": context.opening},
                kind="agent", input=request if self.telemetry.capture_content else None,
                session_id=session_id_for_game(context.game_id, self.package.package_id),
            ) as span:
                response = await self.model(prompt, structured_model=NovelProse)
                prose = NovelProse.model_validate(response.metadata).text.strip()
                if not prose:
                    raise ValueError("novel presenter returned empty prose")
                if self.telemetry.capture_content:
                    span.update(output=prose)
                return prose
        except Exception as error:
            with self.telemetry.span("novel-presentation-fallback",
                                     {"error_type": type(error).__name__},
                                     session_id=session_id_for_game(
                                         context.game_id, self.package.package_id)) as span:
                span.metric("story.novel_presentation_fallback", 1.0)
            if not beats:
                return "我停下来观察眼前的情形，等着下一步行动。"
            parts = []
            for beat in beats:
                speaker = beat["speaker"]
                if speaker:
                    parts.append(f"我听见{speaker}的回应：{beat['text']}")
                else:
                    parts.append(f"我留意到：{beat['text']}")
            return "\n\n".join(parts)
