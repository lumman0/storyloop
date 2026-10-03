"""Second-person player-visible prose from already committed story beats."""

from __future__ import annotations

import json
from collections.abc import Callable

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
                 telemetry: Telemetry | None = None,
                 recent_prose: Callable[[str], list[str]] | None = None) -> None:
        self.package = package
        self.model = model
        self.telemetry = telemetry or LangfuseTelemetry()
        self.formatter = ThinkingSafeOpenAIChatFormatter()
        self.recent_prose = recent_prose

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
            "recent_player_visible_prose": (
                [part[-650:] for part in self.recent_prose(context.game_id)[-3:]]
                if self.recent_prose is not None else []
            ),
            "player_style_preferences": list(current_player_preferences()),
        }
        system = (
            "你是文游主控的小说模式呈现器。把本轮已经发生的玩家可见结果整合为一段连贯的中文小说正文，"
            "以第二人称“你”叙述玩家的行动和所见；无论近期正文使用什么人称，你都统一写“你”。"
            "根据实际事件量控制篇幅：只有选择或短暂停顿时约80至160字；有NPC回应或场景变化时约150至300字。"
            "按可见结果的发生顺序自然串起行动、环境、"
            "时间流逝和NPC回应；可依据公开设定描绘环境氛围，NPC的话可以引用，但不能新增台词或改写其事实含义。"
            "如果 visible_beats 中有 time，利用光线、环境与已经发生的事侧写时段变化；"
            "傍晚或夜深时可让叙述自然显出一天将结束，但不能替玩家决定睡觉或跳天。"
            "不要把第几天、几点或耗时提示写成独立的系统播报；这些数值由界面进度区记录。"
            "current_goal 只用于从已出现的人和事中轻轻引出下一步，不写成任务清单，"
            "也不提前透露尚未发生的节目安排。"
            "玩家行动只以 player_action 为准，不替玩家增加行为、对白、决定、感情或内心独白。"
            "recent_player_visible_prose 只用于衔接刚发生的事和避开重复表达，不要复述它。"
            "每轮优先抓住本轮独有的动作、物件、语气或关系变化；环境描写只选与此刻行动有关的一两处。"
            "若近几轮反复出现窗外、雪光、上午的光、木地板等意象，本轮换用人物动作、声音或物件承接，"
            "不要套用固定的天气或光线开头。"
            "玩家发送私人留言时，准确呈现收件人和原文；除非 visible_beats 明确给出了回信，"
            "不能编造对方已读、即时回应或玩家的心理结论。"
            "不得透露未提供的秘密，不得制造新事件、人物、物品或关系；可用低风险的文学连接词。"
            "玩家画像只微调文风和节奏，不是剧情事实。不要系统提示或建议列表；"
            "不要用第一人称“我”代替玩家叙述，NPC原有的直接引语可以保留其人称。"
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
                prose = prose.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
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
                return "你停下来观察眼前的情形，等着下一步行动。"
            parts = []
            for beat in beats:
                speaker = beat["speaker"]
                if speaker:
                    parts.append(f"你听见{speaker}的回应：{beat['text']}")
                else:
                    parts.append(f"你留意到：{beat['text']}")
            return "\n\n".join(parts)
