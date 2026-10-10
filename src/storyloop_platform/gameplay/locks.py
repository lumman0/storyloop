"""Shared per-player coordination for turn, resume, and settings operations."""

import asyncio
from weakref import WeakValueDictionary


class PlayerTurnLocks:
    def __init__(self) -> None:
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def for_player(self, player_id: str) -> asyncio.Lock:
        lock = self._locks.get(player_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[player_id] = lock
        return lock
