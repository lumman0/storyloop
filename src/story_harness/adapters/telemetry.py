"""Optional, failure-isolated observations for the complete game loop."""

from __future__ import annotations

import functools
import inspect
import os
from collections.abc import Callable
from typing import Protocol


class TraceSpan(Protocol):
    def update(self, **kwargs: object) -> None: ...

    def metric(self, name: str, value: float) -> None: ...


class _NoopSpan:
    def update(self, **kwargs: object) -> None:
        return None

    def metric(self, name: str, value: float) -> None:
        return None


class _SafeContext:
    def __init__(self, client: object | None, name: str, metadata: dict[str, object],
                 kind: str = "span", input: object | None = None,
                 model: str | None = None) -> None:
        self.client = client
        self.name = name
        self.metadata = metadata
        self.kind = kind
        self.input = input
        self.model = model
        self._context: object | None = None

    def __enter__(self) -> TraceSpan:
        if self.client is None:
            return _NoopSpan()
        try:
            kwargs: dict[str, object] = {
                "as_type": self.kind, "name": self.name, "metadata": self.metadata,
            }
            if self.input is not None:
                kwargs["input"] = self.input
            if self.model is not None:
                kwargs["model"] = self.model
            self._context = self.client.start_as_current_observation(**kwargs)
            return _SafeSpan(self._context.__enter__())
        except Exception:
            self._context = None
            return _NoopSpan()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        if self._context is not None:
            try:
                self._context.__exit__(exc_type, exc, traceback)
            except Exception:
                pass
        return False


class _SafeSpan:
    def __init__(self, span: object) -> None:
        self.span = span

    def update(self, **kwargs: object) -> None:
        try:
            self.span.update(**kwargs)
        except Exception:
            pass

    def metric(self, name: str, value: float) -> None:
        try:
            self.span.score_trace(name=name, value=value, data_type="NUMERIC")
        except Exception:
            pass


class Telemetry(Protocol):
    capture_content: bool

    def span(self, name: str, metadata: dict[str, object], *, kind: str = "span",
             input: object | None = None, model: str | None = None) -> _SafeContext: ...

    def flush(self) -> None: ...


class LangfuseTelemetry:
    def __init__(self, client: object | None = None, capture_content: bool = False) -> None:
        self.client = client
        self.capture_content = capture_content

    def span(self, name: str, metadata: dict[str, object], *, kind: str = "span",
             input: object | None = None, model: str | None = None) -> _SafeContext:
        return _SafeContext(self.client, name, metadata, kind, input, model)

    def flush(self) -> None:
        if self.client is not None:
            try:
                self.client.flush()
            except Exception:
                pass


def observed_tool(tool: Callable, telemetry: Telemetry) -> Callable:
    """Wrap an AgentScope tool so its invocation is a child observation."""
    @functools.wraps(tool)
    def wrapper(*args: object, **kwargs: object) -> object:
        arguments = inspect.signature(tool).bind(*args, **kwargs).arguments
        with telemetry.span(
            f"tool:{tool.__name__}", {"tool": tool.__name__}, kind="tool",
            input=dict(arguments) if telemetry.capture_content else None,
        ) as span:
            result = tool(*args, **kwargs)
            if telemetry.capture_content:
                span.update(output=str(result))
            return result

    return wrapper


def configured_telemetry() -> LangfuseTelemetry:
    """Enable Langfuse only when its SDK and environment are configured."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if bool(public_key) != bool(secret_key):
        raise ValueError("set both LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY")
    if not public_key:
        return LangfuseTelemetry()
    try:
        from langfuse import get_client
    except ImportError as error:
        raise RuntimeError("install the observability extra to enable Langfuse") from error
    return LangfuseTelemetry(
        get_client(),
        capture_content=os.getenv("STORY_TRACE_CONTENT", "").lower() in {"1", "true", "yes"},
    )
