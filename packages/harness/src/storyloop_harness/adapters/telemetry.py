"""Optional telemetry ports; the library has no telemetry service configuration."""
from __future__ import annotations
from contextlib import nullcontext
from hashlib import sha256
from typing import ContextManager, Protocol


def session_id_for_game(game_id: str, scenario_id: str | None = None) -> str:
    candidate = f'{scenario_id}:{game_id}' if scenario_id else game_id
    return candidate if candidate.isascii() and len(candidate) <= 200 else 'game-' + sha256(candidate.encode('utf-8')).hexdigest()


class TraceSpan(Protocol):
    def update(self, **kwargs: object) -> None: ...
    def metric(self, name: str, value: float) -> None: ...


class Telemetry(Protocol):
    capture_content: bool
    def span(self, name: str, metadata: dict[str, object], *, kind: str = 'span',
             input: object | None = None, model: str | None = None,
             session_id: str | None = None) -> ContextManager[TraceSpan]: ...
    def flush(self) -> None: ...


class _NoopSpan:
    def update(self, **kwargs: object) -> None:
        pass
    def metric(self, name: str, value: float) -> None:
        pass


class NoopTelemetry:
    capture_content = False
    def span(self, name: str, metadata: dict[str, object], **kwargs: object) -> ContextManager[TraceSpan]:
        return nullcontext(_NoopSpan())
    def flush(self) -> None:
        pass
