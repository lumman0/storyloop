"""Late-bound model configuration for OpenAI-compatible NPC endpoints."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from agentscope.model import OpenAIChatModel


ToolChoicePolicy = Literal["native", "auto_only"]


class CompatibleOpenAIChatModel(OpenAIChatModel):
    """Adapt forced tool choices for endpoints that only accept auto/none."""

    def __init__(self, *args: object, tool_choice_policy: ToolChoicePolicy = "native", **kwargs: object) -> None:
        self.tool_choice_policy = tool_choice_policy
        super().__init__(*args, **kwargs)

    async def __call__(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        structured_model: type | None = None,
        **kwargs: object,
    ):
        if self.tool_choice_policy == "auto_only" and structured_model is None:
            if tool_choice not in (None, "auto", "none"):
                tool_choice = "auto"
        return await super().__call__(
            messages, tools=tools, tool_choice=tool_choice,
            structured_model=structured_model, **kwargs,
        )


@dataclass(frozen=True)
class NpcModelConfig:
    model_name: str
    api_key: str = field(repr=False)
    base_url: str | None = None
    tool_choice_policy: ToolChoicePolicy = "native"

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> NpcModelConfig:
        values = os.environ if env is None else env
        model_name = values.get("STORY_NPC_MODEL", "").strip()
        api_key = values.get("STORY_NPC_API_KEY", "") or values.get("OPENAI_API_KEY", "")
        base_url = values.get("STORY_NPC_BASE_URL", "").strip() or None
        if not model_name:
            raise ValueError("set STORY_NPC_MODEL before live play")
        if not api_key:
            raise ValueError("set STORY_NPC_API_KEY or OPENAI_API_KEY before live play")
        return cls(model_name, api_key, base_url)

    def create_model(self) -> OpenAIChatModel:
        if self.tool_choice_policy not in ("native", "auto_only"):
            raise ValueError(f"unsupported tool_choice_policy: {self.tool_choice_policy}")
        client_kwargs = {"base_url": self.base_url} if self.base_url else None
        return CompatibleOpenAIChatModel(
            model_name=self.model_name,
            api_key=self.api_key,
            stream=False,
            client_kwargs=client_kwargs,
            tool_choice_policy=self.tool_choice_policy,
        )


BAILIAN_TOKEN_PLAN_URL = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

LIGHT_TASKS = frozenset({"npc_selection", "entity_extraction", "intent_classification", "work_selection"})
DEEP_TASKS = frozenset({"npc_reply", "main_react", "adjudication", "narration"})


@dataclass(frozen=True)
class BailianModelRouter:
    """Task-level model choice for the user's Token Plan interactive harness."""

    api_key: str = field(repr=False)
    base_url: str = BAILIAN_TOKEN_PLAN_URL
    light_model: str = "qwen3.8-flash"
    deep_model: str = "qwen3.8-max"

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> BailianModelRouter:
        values = os.environ if env is None else env
        api_key = values.get("STORY_BAILIAN_API_KEY", "") or values.get("STORY_NPC_API_KEY", "")
        if not api_key:
            raise ValueError("set STORY_BAILIAN_API_KEY before live play")
        return cls(
            api_key=api_key,
            base_url=values.get("STORY_BAILIAN_BASE_URL", "").strip() or BAILIAN_TOKEN_PLAN_URL,
            light_model=values.get("STORY_LIGHT_MODEL", "").strip() or "qwen3.8-flash",
            deep_model=values.get("STORY_DEEP_MODEL", "").strip() or "qwen3.8-max",
        )

    def create_model(self, task: str) -> OpenAIChatModel:
        if task in LIGHT_TASKS:
            name = self.light_model
        elif task in DEEP_TASKS:
            name = self.deep_model
        else:
            raise ValueError(f"unknown model task: {task}")
        return NpcModelConfig(name, self.api_key, self.base_url, "auto_only").create_model()
