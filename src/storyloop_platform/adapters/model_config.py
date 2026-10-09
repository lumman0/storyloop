"""Late-bound model configuration for OpenAI-compatible NPC endpoints."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal
from types import SimpleNamespace

from agentscope.credential import OpenAICredential
from agentscope.message import Msg as AgentScopeMsg, SystemMsg, UserMsg
from agentscope.model import OpenAIChatModel
from agentscope.tool import ToolChoice
from httpx2 import Timeout

from storyloop_platform.adapters.telemetry import LangfuseTelemetry, Telemetry
from storyloop_harness.generation import ThinkingSafeOpenAIChatFormatter
from storyloop_platform.portal.billing import record_model_usage


from storyloop_harness.generation import CompatibleOpenAIChatModel, ToolChoicePolicy, StructuredOutputTransport


@dataclass(frozen=True)
class NpcModelConfig:
    model_name: str
    api_key: str = field(repr=False)
    base_url: str | None = None
    tool_choice_policy: ToolChoicePolicy = "native"
    telemetry: Telemetry | None = field(default=None, repr=False)
    task: str = "model"
    timeout_seconds: float = 90
    connect_timeout_seconds: float = 10
    max_retries: int = 2
    generate_kwargs: Mapping[str, object] = field(default_factory=dict, repr=False)
    structured_output_transport: StructuredOutputTransport = "auto"

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
        client_kwargs = {
            "timeout": Timeout(self.timeout_seconds, connect=self.connect_timeout_seconds),
            "max_retries": self.max_retries,
        }
        parameters = {key: value for key, value in self.generate_kwargs.items()
                      if key in OpenAIChatModel.Parameters.model_fields}
        extra_body = self.generate_kwargs.get("extra_body")
        return CompatibleOpenAIChatModel(
            credential=OpenAICredential(api_key=self.api_key, base_url=self.base_url),
            model=self.model_name,
            stream=False,
            max_retries=self.max_retries,
            client_kwargs=client_kwargs,
            parameters=OpenAIChatModel.Parameters(**parameters),
            extra_body=extra_body if isinstance(extra_body, dict) else None,
            formatter=ThinkingSafeOpenAIChatFormatter(),
            tool_choice_policy=self.tool_choice_policy,
            structured_output_transport=self.structured_output_transport,
            telemetry=self.telemetry,
            task=self.task,
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
