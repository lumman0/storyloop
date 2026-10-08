"""AgentScope model adaptation; callers supply configured credentials."""
from __future__ import annotations
from typing import Literal
from types import SimpleNamespace
from agentscope.message import Msg as AgentScopeMsg, SystemMsg, UserMsg
from agentscope.model import OpenAIChatModel
from agentscope.tool import ToolChoice
from storyloop_harness.adapters.telemetry import NoopTelemetry, Telemetry
from storyloop_harness.models.usage import record_model_usage

ToolChoicePolicy = Literal["native", "auto_only"]
StructuredOutputTransport = Literal["auto", "tool_call"]


class CompatibleOpenAIChatModel(OpenAIChatModel):
    """Adapt forced tool choices for endpoints that only accept auto/none."""

    def __init__(self, *args: object, tool_choice_policy: ToolChoicePolicy = "native",
                 structured_output_transport: StructuredOutputTransport = "auto",
                 telemetry: Telemetry | None = None, task: str = "model", **kwargs: object) -> None:
        if structured_output_transport not in ("auto", "tool_call"):
            raise ValueError("unsupported structured_output_transport")
        self.tool_choice_policy = tool_choice_policy
        self.telemetry = telemetry or NoopTelemetry()
        self.task = task
        super().__init__(*args, **kwargs)

    @property
    def model_name(self) -> str:
        return self.model

    @staticmethod
    def _messages(messages: list) -> list[AgentScopeMsg]:
        converted = []
        for item in messages:
            if isinstance(item, AgentScopeMsg):
                converted.append(item)
            elif isinstance(item, dict):
                content = item.get("content", "")
                if isinstance(content, list):
                    content = "\n".join(part.get("text", "") for part in content
                                        if isinstance(part, dict))
                if item.get("role") == "system":
                    converted.append(SystemMsg(name=item.get("name", "system"), content=content or ""))
                else:
                    converted.append(UserMsg(name=item.get("name", "user"), content=content or ""))
            else:
                raise TypeError("model messages must be AgentScope messages or OpenAI message dicts")
        return converted

    def _record_usage(self, response: object) -> None:
        usage = getattr(response, "usage", None)
        record_model_usage(self.model, self.task, usage)

    async def _call_api(self, model_name: str, messages: list, tools=None,
                        tool_choice=None, **kwargs: object):
        if self.tool_choice_policy == "auto_only" and tool_choice is not None:
            if tool_choice.mode not in ("auto", "none"):
                tool_choice = ToolChoice(mode="auto")
        return await super()._call_api(model_name, messages, tools, tool_choice, **kwargs)

    async def generate_structured_output(self, messages: list, structured_model: type, **kwargs: object):
        messages = self._messages(messages)
        with self.telemetry.span(
            f"model:{self.task}", {"task": self.task,
                                  "structured_model": structured_model.__name__},
            kind="generation", model=self.model,
            input=messages if self.telemetry.capture_content else None,
        ) as generation:
            try:
                response = await super().generate_structured_output(
                    messages, structured_model, **kwargs,
                )
            except Exception as error:
                generation.update(level="ERROR", status_message=type(error).__name__)
                raise
            self._record_usage(response)
            if response.usage is not None:
                generation.update(usage_details={"input": response.usage.input_tokens,
                                                 "output": response.usage.output_tokens})
            if self.telemetry.capture_content:
                generation.update(output=response.content)
            return response

    async def __call__(
        self,
        messages: list,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        structured_model: type | None = None,
        **kwargs: object,
    ):
        if structured_model is not None:
            response = await self.generate_structured_output(messages, structured_model, **kwargs)
            return SimpleNamespace(metadata=response.content, usage=response.usage,
                                   content=response.content)
        if isinstance(tool_choice, str):
            tool_choice = ToolChoice(mode=tool_choice)
        if self.tool_choice_policy == "auto_only" and tool_choice is not None:
            if tool_choice.mode not in ("auto", "none"):
                tool_choice = ToolChoice(mode="auto")
        messages = self._messages(messages)
        with self.telemetry.span(
            f"model:{self.task}",
            {"task": self.task, "tool_choice": tool_choice,
             "available_tools": [item.get("function", {}).get("name", "") for item in tools or []],
             "structured_model": getattr(structured_model, "__name__", None)},
            kind="generation", model=self.model,
            input=messages if self.telemetry.capture_content else None,
        ) as generation:
            try:
                response = await super().__call__(
                    messages, tools=tools, tool_choice=tool_choice,
                    **kwargs,
                )
                self._record_usage(response)
            except Exception as error:
                generation.update(level="ERROR", status_message=type(error).__name__)
                raise
            if response.usage is not None:
                generation.update(usage_details={
                    "input": response.usage.input_tokens,
                    "output": response.usage.output_tokens,
                })
            if self.telemetry.capture_content:
                generation.update(output=response.content)
            return response
