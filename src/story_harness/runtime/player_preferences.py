"""Player-only presentation hints for a single turn, never NPC knowledge."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator


_current: ContextVar[tuple[str, ...]] = ContextVar("story_player_preferences", default=())


def current_player_preferences() -> tuple[str, ...]:
    return _current.get()


@contextmanager
def player_preferences_scope(items: tuple[str, ...]) -> Iterator[None]:
    token = _current.set(items[:8])
    try:
        yield
    finally:
        _current.reset(token)
