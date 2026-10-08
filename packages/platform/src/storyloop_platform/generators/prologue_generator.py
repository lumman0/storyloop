"""Generate a player-visible prologue once while publishing a scenario version."""

from __future__ import annotations

import json

from storyloop_harness.adapters.agentscope_message import Msg
from agentscope.model import ChatModelBase
from pydantic import BaseModel, Field

from storyloop_platform.adapters.telemetry import LangfuseTelemetry, Telemetry
from storyloop_harness.agents.openai_formatter import ThinkingSafeOpenAIChatFormatter
from storyloop_platform.runtime.campaign import CampaignProgram
from storyloop_harness import ScenarioPackage


class GeneratedPrologue(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class ModelPrologueGenerator:
    """Use only material the player may know at the start of the story."""

    def __init__(self, model: ChatModelBase, telemetry: Telemetry | None = None) -> None:
        self.model = model
        self.telemetry = telemetry or LangfuseTelemetry()
        self.formatter = ThinkingSafeOpenAIChatFormatter()

    async def generate(self, package: ScenarioPackage, program: CampaignProgram | None,
                       title: str, summary: str) -> str:
        opening_scenes: list[str] = []
        if program is not None:
            for step in program.steps:
                if step["at"] > 0 or step["kind"] in {"continue", "choice", "message"}:
                    break
                if step["kind"] == "scene" and step["text"].strip():
                    opening_scenes.append(step["text"][:1500])
                if len(opening_scenes) == 3:
                    break
        player_state = package.initial_state.get("player_profile", {})
        if not isinstance(player_state, dict):
            player_state = {}
        request = {
            "title": title,
            "summary": summary,
            "opening": (package.story_blueprint.opening_focus[:3500]
                        if package.story_blueprint is not None else package.opening[:3500]),
            "opening_scenes": opening_scenes,
            "public_setting": [entry.text[:1200] for entry in
                               package.worldbook.visible_lore("player", limit=6)],
            "player_profile": player_state,
            "presentation_mode": ("novel" if program is not None
                                  or package.story_blueprint is not None else "interactive"),
        }
        system = (
            "你为文游剧本撰写固定的玩家可见序章。只依据所给公开资料和开场场景，"
            "介绍世界背景、玩家角色已经确定的身份与处境、眼前可做的事；"
            "主角姓名、年龄、学校和性格只有在资料明确给出时才可写。资料未设定主角时，"
            "用不限定身份的方式介绍玩家位置，不要擅自创造角色卡。"
            "用 300 至 650 字的连贯中文叙事，分 3 至 5 段；不要重复后续章节，"
            "不要提前揭晓未登场人物、隐藏事件或真相，也不要替玩家做出首次决定。"
            "无论 presentation_mode 为 novel 还是 interactive，都以第二人称“你”叙述玩家；"
            "只有人物的直接引语可以保留原本的人称。"
            "末段自然引向当前可行动的情境，不要写选项列表或系统提示。"
            "返回 JSON 结构化结果，text 中用真正的换行符分段。"
        )
        prompt = await self.formatter.format(msgs=[
            Msg("system", system, "system"),
            Msg("author", json.dumps(request, ensure_ascii=False), "user"),
        ])
        with self.telemetry.span(
            "scenario-prologue-model",
            {"scenario_id": package.package_id, "scenario_version": package.version},
            kind="agent", input=request if self.telemetry.capture_content else None,
        ) as span:
            response = await self.model(prompt, structured_model=GeneratedPrologue)
            prose = GeneratedPrologue.model_validate(response.metadata).text.strip()
            prose = prose.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
            if not prose:
                raise ValueError("prologue model returned empty text")
            if package.story_blueprint is not None:
                prose = "{{player_intro}}\n\n" + prose
            if self.telemetry.capture_content:
                span.update(output=prose)
            return prose
