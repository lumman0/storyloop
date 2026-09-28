"""Optional Langfuse spans that never become a game-state dependency."""

from __future__ import annotations

from typing import Protocol


class TraceSpan(Protocol):
    def update(self, **kwargs: object) -> None: ...


class _NoopSpan:
    def update(self, **kwargs: object) -> None:
        return None


class _SafeContext:
    def __init__(self, client: object | None, name: str, metadata: dict[str, object]) -> None:
        self.client = client
        self.name = name
        self.metadata = metadata
        self._context: object | None = None

    def __enter__(self) -> TraceSpan:
        if self.client is None:
            return _NoopSpan()
        try:
            self._context = self.client.start_as_current_observation(
                as_type="span", name=self.name, metadata=self.metadata
            )
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


class Telemetry(Protocol):
    def span(self, name: str, metadata: dict[str, object]) -> _SafeContext: ...


class LangfuseTelemetry:
    def __init__(self, client: object | None = None) -> None:
        self.client = client

    def span(self, name: str, metadata: dict[str, object]) -> _SafeContext:
        return _SafeContext(self.client, name, metadata)


def configured_telemetry() -> LangfuseTelemetry:
    """Enable Langfuse only when its SDK and environment are configured."""
    import os

    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return LangfuseTelemetry()
    try:
        from langfuse import get_client
    except ImportError as error:
        raise RuntimeError("install the observability extra to enable Langfuse") from error
    return LangfuseTelemetry(get_client())
