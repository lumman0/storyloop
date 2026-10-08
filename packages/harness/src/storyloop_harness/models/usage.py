"""Model token usage, independent of pricing and accounts."""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator

@dataclass(frozen=True)
class ModelUsage:
    model: str
    task: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0

    def __post_init__(self) -> None:
        if (not self.model or not self.task or any(type(value) is not int or value < 0 for value in
               (self.input_tokens, self.output_tokens, self.cached_input_tokens))
                or self.cached_input_tokens > self.input_tokens):
            raise ValueError("invalid model token usage")

    def to_dict(self) -> dict[str, str | int]:
        return {"model": self.model, "task": self.task, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "cached_input_tokens": self.cached_input_tokens}


@dataclass
class UsageCollector:
    records: list[ModelUsage] = field(default_factory=list)

    def record(self, model: str, task: str, usage: object) -> None:
        if usage is None:
            raise RuntimeError("model did not report token usage; turn cannot be billed accurately")
        details = getattr(usage, "metadata", None)
        prompt_details = ((details.get("prompt_tokens_details") or details.get("input_tokens_details"))
                          if isinstance(details, dict) else
                          (getattr(details, "prompt_tokens_details", None)
                           or getattr(details, "input_tokens_details", None)))
        cached = getattr(usage, "cache_input_tokens", None)
        if type(cached) is not int:
            cached = (prompt_details.get("cached_tokens") if isinstance(prompt_details, dict)
                      else getattr(prompt_details, "cached_tokens", None))
        self.records.append(ModelUsage(model, task, usage.input_tokens, usage.output_tokens,
                                       cached if type(cached) is int else 0))


_active_usage: ContextVar[UsageCollector | None] = ContextVar("story_billing_usage", default=None)


@contextmanager
def collect_usage() -> Iterator[UsageCollector]:
    collector = UsageCollector()
    token = _active_usage.set(collector)
    try:
        yield collector
    finally:
        _active_usage.reset(token)


def record_model_usage(model: str, task: str, usage: object) -> None:
    collector = _active_usage.get()
    if collector is not None:
        collector.record(model, task, usage)
