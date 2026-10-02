"""Optional player-facing events emitted during a turn."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any


TurnProgress = Callable[[dict[str, Any]], Awaitable[None]]
logger = logging.getLogger(__name__)


async def emit(progress: TurnProgress | None, event_type: str, **payload: Any) -> None:
    if progress is not None:
        try:
            await progress({"type": event_type, **payload})
        except Exception:
            logger.warning("turn progress delivery failed", exc_info=True)
