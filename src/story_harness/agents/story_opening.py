"""Generate one save-specific opening from source-grounded story data."""

from __future__ import annotations

import json

from agentscope.message import Msg
from agentscope.model import ChatModelBase
from pydantic import BaseModel, Field, field_validator

from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry, session_id_for_game
from story_harness.agents.openai_formatter import ThinkingSafeOpenAIChatFormatter
from story_harness.world.scenario import ScenarioPackage


class OpeningActor(BaseModel):
    actor_id: str
    name: str = Field(min_length=1, max_length=40)
    role_card: str = Field(min_length=20, max_length=1000)
    public_profile: str = Field(min_length=10, max_length=400)


class OpeningOption(BaseModel):
    label: str = Field(min_length=2, max_length=50)
    input: str = Field(min_length=2, max_length=500)


class GeneratedStoryOpening(BaseModel):
    prose: str = Field(min_length=100, max_length=5000)
    player_profile: dict[str, str]
    actors: list[OpeningActor]
    options: list[OpeningOption] = Field(min_length=3, max_length=3)

    @field_validator("player_profile")
    @classmethod
    def named_player(cls, value: dict[str, str]) -> dict[str, str]:
        if not value.get("name", "").strip():
            raise ValueError("generated player profile requires a name")
        return value

    def save_state(self, setup: dict[str, str]) -> dict[str, object]:
        profile = dict(self.player_profile)
        if setup["player"] == "custom":
            profile.update({key: value for key, value in setup.items()
                            if key not in {"player", "tone"}})
        return {
            "player_profile": profile,
            "story_setup": dict(setup),
            "actor_profiles": {actor.actor_id: {
                "name": actor.name, "role_card": actor.role_card,
                "public_profile": actor.public_profile,
            } for actor in self.actors},
        }


class StoryOpeningGenerator:
    def __init__(self, model: ChatModelBase, telemetry: Telemetry | None = None) -> None:
        self.model = model
        self.telemetry = telemetry or LangfuseTelemetry()
        self.formatter = ThinkingSafeOpenAIChatFormatter()

    async def generate(self, game_id: str, package: ScenarioPackage, title: str,
                       setup: dict[str, str]) -> GeneratedStoryOpening:
        blueprint = package.story_blueprint
        if blueprint is None:
            raise ValueError("source-driven opening requires a story blueprint")
        player = next(option for option in blueprint.setup.player_options
                      if option.id == setup["player"])
        tone = next(option for option in blueprint.setup.tone_options
                    if option.id == setup["tone"])
        request = {
            "title": title,
            "source_document": blueprint.source_document,
            "opening_focus": blueprint.opening_focus,
            "source_facts": blueprint.relevant_facts(1, ""),
            "source_resolutions": blueprint.source_resolutions,
            "player_start": player.guidance,
            "tone": tone.guidance,
            "custom_player_fields": {key: value for key, value in setup.items()
                                     if key not in {"player", "tone"}},
            "actor_slots": [slot.model_dump() for slot in blueprint.actor_slots],
        }
        system = (
            "你是互动故事的主叙述者。根据剧本原始文档整理出的资料，为这个新存档生成一次开场。"
            "生成玩家角色卡与全部嘉宾角色卡；每个 actor_slot 恰好生成一个演员，actor_id 原样返回。"
            "随机开局时创造具体而不雷同的人物；自定义开局时严格保留玩家给出的身份。"
            "角色卡可包含角色自己的秘密，但 public_profile 只包含此刻玩家能看到的外貌和举止。"
            "prose 用第二人称写一段连贯、有动作和场景细节的序章，以当前可行动的场面结束。"
            "自然交代玩家的可见身份和为何来到此处；用行李、镜头、陌生人的短暂反应等具体细节"
            "承载陌生人初见的气氛，不把人物性格写成标签清单。"
            "只依据 source_facts、source_resolutions 和 opening_focus，"
            "当原文说法冲突时遵循 source_resolutions；不擅自公布尚未公开的身份或未来事件；"
            "不替玩家说话、作关键选择或直接跳过当天。"
            "给出三个紧贴开场事件的可选行动，玩家也能自由输入。"
            "不要使用系统模板、属性表或剧情流程播报。输出 GeneratedStoryOpening。"
        )
        prompt = await self.formatter.format(msgs=[
            Msg("system", system, "system"),
            Msg("source", json.dumps(request, ensure_ascii=False), "user"),
        ])
        with self.telemetry.span(
            "source-story-opening", {"game_id": game_id,
                                     "scenario_id": package.package_id},
            kind="agent", input=request if self.telemetry.capture_content else None,
            session_id=session_id_for_game(game_id, package.package_id),
        ) as span:
            response = await self.model(prompt, structured_model=GeneratedStoryOpening)
            opening = GeneratedStoryOpening.model_validate(response.metadata)
            expected = {slot.actor_id for slot in blueprint.actor_slots}
            actual = [actor.actor_id for actor in opening.actors]
            if len(actual) != len(expected) or set(actual) != expected:
                raise ValueError("generated opening did not cover every actor slot")
            if len({actor.name for actor in opening.actors}) != len(actual):
                raise ValueError("generated opening has duplicate actor names")
            if (setup["player"] == "custom" and setup.get("name")
                    and opening.player_profile["name"] != setup["name"]):
                raise ValueError("generated opening changed the player's chosen name")
            if opening.player_profile["name"] in {actor.name for actor in opening.actors}:
                raise ValueError("generated player and actor names must differ")
            span.metric("story.opening_model_calls", 1.0)
            if self.telemetry.capture_content:
                span.update(output=opening.model_dump())
            return opening
