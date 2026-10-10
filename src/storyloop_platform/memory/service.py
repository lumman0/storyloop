"""Optional player profile collection, cached preferences, and worker lifecycle."""

from __future__ import annotations

import asyncio
import logging

from storyloop_harness.telemetry import Telemetry, session_id_for_game
from storyloop_platform.memory.jobs import MemoryBatch, PlayerMemoryJobs
from storyloop_platform.memory.providers import PlayerMemory


class PlayerMemoryService:
    def __init__(self, provider: PlayerMemory | None, jobs: PlayerMemoryJobs,
                 enabled: bool, telemetry: Telemetry) -> None:
        self.provider = provider
        self.jobs = jobs
        self.enabled = enabled
        self.telemetry = telemetry
        self._profile_cache: dict[str, tuple[str, ...]] = {}
        self._memory_access = asyncio.Lock()
        self._memory_wakeup = asyncio.Event()

    def close(self) -> None:
        if self.provider is not None:
            self.provider.close()

    async def status(self, player_id: str) -> dict:
        available = self.enabled and self.provider is not None
        enabled = available and self.jobs.enabled(player_id)
        memories = (await asyncio.to_thread(self.provider.list_memories, player_id)
                    if self.provider is not None else [])
        return {"available": available, "enabled": enabled, "memories": memories,
                "queued_inputs": self.jobs.pending_count(player_id),
                "batch_size": 6, "min_interval_hours": 12,
                "charged_points": 0}

    async def set_enabled(self, player_id: str, enabled: bool) -> dict:
        if enabled and not self.enabled:
            raise ValueError("玩家画像尚未由平台开放")
        async with self._memory_access:
            self.jobs.set_enabled(player_id, enabled)
            self._profile_cache.pop(player_id, None)
        return await self.status(player_id)

    async def clear(self, player_id: str) -> dict:
        if self.provider is None:
            raise ValueError("玩家画像当前不可用")
        async with self._memory_access:
            self.jobs.clear(player_id)
            await asyncio.to_thread(self.provider.clear, player_id)
            self._profile_cache.pop(player_id, None)
        return await self.status(player_id)

    async def preferences_for(self, player_id: str) -> tuple[str, ...]:
        if not self.enabled or self.provider is None or not self.jobs.enabled(player_id):
            return ()
        if player_id in self._profile_cache:
            return self._profile_cache[player_id]
        try:
            rows = await asyncio.to_thread(self.provider.list_memories, player_id)
            result = tuple(row["text"][:180] for row in rows[:8])
            self._profile_cache[player_id] = result
            return result
        except Exception:
            logging.getLogger(__name__).exception("player profile read failed")
            return ()

    def queue_input(self, player_id: str, game_id: str,
                    request_id: str, player_text: str) -> None:
        if not self.enabled or self.provider is None:
            return
        if player_text == "/continue" or player_text in {"/next", "/rest"} or player_text.startswith("/choose "):
            return
        try:
            if self.jobs.enqueue(player_id, game_id, request_id, player_text):
                self._memory_wakeup.set()
        except Exception:
            logging.getLogger(__name__).exception("player profile enqueue failed")

    async def run_worker(self) -> None:
        if not self.enabled or self.provider is None:
            return
        while True:
            task = asyncio.create_task(self._run_batch())
            try:
                batch = await asyncio.shield(task)
            except asyncio.CancelledError:
                # Finish the claimed batch before closing its embedded Qdrant store.
                try:
                    await task
                except Exception:
                    logging.getLogger(__name__).exception("player profile batch failed during shutdown")
                raise
            except Exception:
                logging.getLogger(__name__).exception("player profile worker failed; retrying")
                batch = None
            if batch is None:
                self._memory_wakeup.clear()
                try:
                    await asyncio.wait_for(self._memory_wakeup.wait(), timeout=20)
                except asyncio.TimeoutError:
                    pass

    async def _run_batch(self) -> MemoryBatch | None:
        async with self._memory_access:
            batch = await asyncio.to_thread(self.jobs.claim)
            if batch is None:
                return None
            with self.telemetry.span(
                "player-memory-batch", {"input_count": len(batch.items),
                                        "provider": "mem0", "billed_to_player": False},
                session_id=session_id_for_game(batch.items[0][0]),
            ) as span:
                try:
                    await asyncio.to_thread(
                        self.provider.remember, batch.player_id,
                        tuple(item[2] for item in batch.items),
                    )
                except Exception:
                    span.metric("story.player_memory_batch_success", 0.0)
                    logging.getLogger(__name__).exception("player profile extraction failed")
                    await asyncio.to_thread(self.jobs.fail, batch)
                else:
                    await asyncio.to_thread(self.jobs.complete, batch)
                    self._profile_cache.pop(batch.player_id, None)
                    span.metric("story.player_memory_batch_success", 1.0)
            return batch
