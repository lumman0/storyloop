"""Player memory policy is testable without auth, a database, or model calls."""

import asyncio
import threading
from contextlib import nullcontext

import pytest

from storyloop_platform.lifecycle import OperationSupervisor
from storyloop_platform.memory.jobs import MemoryBatch
from storyloop_platform.memory.service import PlayerMemoryService


class FakeMemory:
    def __init__(self):
        self.rows = {}
        self.reads = 0
        self.closed = False
        self.error = False
        self.remembered = []

    def list_memories(self, player_id):
        self.reads += 1
        if self.error:
            raise RuntimeError("read failed")
        return self.rows.get(player_id, [])

    def remember(self, player_id, inputs):
        if self.error:
            raise RuntimeError("extraction failed")
        self.remembered.append((player_id, inputs))

    def clear(self, player_id):
        self.rows.pop(player_id, None)

    def close(self):
        self.closed = True


class FakeJobs:
    def __init__(self):
        self.settings = set()
        self.inputs = []
        self.batches = []
        self.completed = []
        self.failed = []
        self.settled = threading.Event()

    def enabled(self, player_id):
        return player_id in self.settings

    def set_enabled(self, player_id, enabled):
        if enabled:
            self.settings.add(player_id)
        else:
            self.settings.discard(player_id)
            self.clear(player_id)

    def enqueue(self, player_id, game_id, request_id, player_text):
        if not self.enabled(player_id):
            return False
        self.inputs.append((player_id, game_id, request_id, player_text))
        return True

    def pending_count(self, player_id):
        return sum(item[0] == player_id for item in self.inputs)

    def clear(self, player_id):
        self.inputs = [item for item in self.inputs if item[0] != player_id]

    def claim(self):
        return self.batches.pop(0) if self.batches else None

    def complete(self, batch):
        self.completed.append(batch)
        self.settled.set()

    def fail(self, batch):
        self.failed.append(batch)
        self.settled.set()


class FakeTelemetry:
    def __init__(self):
        self.spans = []
        self.metrics = []

    def span(self, name, metadata, **kwargs):
        self.spans.append((name, metadata, kwargs))
        return nullcontext(self)

    def metric(self, name, value):
        self.metrics.append((name, value))


def test_status_collection_cache_and_clear_are_player_scoped():
    async def run():
        memory, jobs = FakeMemory(), FakeJobs()
        service = PlayerMemoryService(memory, jobs, True, FakeTelemetry(), OperationSupervisor())
        memory.rows["first"] = [{"text": "slow pacing"}]
        assert (await service.status("first"))["enabled"] is False
        service.queue_input("first", "game", "before", "I prefer slow pacing")
        assert jobs.inputs == []
        assert (await service.set_enabled("first", True))["enabled"] is True
        service.queue_input("first", "game", "request", "I prefer slow pacing")
        assert (await service.status("first"))["queued_inputs"] == 1
        assert await service.preferences_for("first") == ("slow pacing",)
        reads = memory.reads
        assert await service.preferences_for("first") == ("slow pacing",)
        assert memory.reads == reads
        assert await service.preferences_for("second") == ()
        await service.set_enabled("first", False)
        assert jobs.inputs == []
        memory.rows["first"] = [{"text": "new preference"}]
        await service.set_enabled("first", True)
        assert await service.preferences_for("first") == ("new preference",)
        service.enabled = False
        status = await service.status("first")
        assert status["available"] is False and status["memories"]
        assert status["charged_points"] == 0
        assert await service.preferences_for("first") == ()
        service.queue_input("first", "game", "disabled", "I prefer slower pacing")
        assert jobs.pending_count("first") == 0
        with pytest.raises(ValueError):
            await service.set_enabled("first", True)
        assert (await service.clear("first"))["memories"] == []
        assert jobs.pending_count("first") == 0
        service.enabled = True
        assert await service.preferences_for("first") == ()
        service.close()
        assert memory.closed
    asyncio.run(run())


def test_preferences_are_bounded_and_optional_read_failure_degrades_safely():
    async def run():
        memory, jobs = FakeMemory(), FakeJobs()
        jobs.set_enabled("player", True)
        service = PlayerMemoryService(memory, jobs, True, FakeTelemetry(), OperationSupervisor())
        memory.error = True
        assert await service.preferences_for("player") == ()
        memory.error = False
        memory.rows["player"] = [{"text": "a" * 200}] * 10
        assert await service.preferences_for("player") == ("a" * 180,) * 8
    asyncio.run(run())


def test_campaign_controls_are_not_collected():
    memory, jobs = FakeMemory(), FakeJobs()
    jobs.set_enabled("player", True)
    service = PlayerMemoryService(memory, jobs, True, FakeTelemetry(), OperationSupervisor())
    for text in ("/continue", "/next", "/rest", "/choose a 一句话"):
        service.queue_input("player", "game", text, text)
    service.queue_input("player", "game", "speech", "我喜欢慢慢认识人。")
    assert jobs.inputs == [("player", "game", "speech", "我喜欢慢慢认识人。")]


@pytest.mark.parametrize("fails", [False, True])
def test_worker_settles_extraction_and_does_not_bill_player(fails):
    async def run():
        memory, jobs, telemetry = FakeMemory(), FakeJobs(), FakeTelemetry()
        jobs.set_enabled("player", True)
        memory.rows["player"] = [{"text": "old preference"}]
        batch = MemoryBatch("player", tuple(("game", str(i), "slow pacing") for i in range(6)))
        jobs.batches.append(batch)
        service = PlayerMemoryService(memory, jobs, True, telemetry, OperationSupervisor())
        assert await service.preferences_for("player") == ("old preference",)
        memory.rows["player"] = [{"text": "new preference"}]
        memory.error = fails
        worker = asyncio.create_task(service.run_worker())
        try:
            assert await asyncio.to_thread(jobs.settled.wait, 5)
        finally:
            worker.cancel()
            with pytest.raises(asyncio.CancelledError):
                await worker
        assert jobs.failed == ([batch] if fails else [])
        assert jobs.completed == ([] if fails else [batch])
        memory.error = False
        assert await service.preferences_for("player") == (("old preference",) if fails else ("new preference",))
        assert telemetry.spans[0][1]["billed_to_player"] is False
        assert telemetry.metrics == [("story.player_memory_batch_success", float(not fails))]
    asyncio.run(run())


def test_worker_shutdown_finishes_claimed_batch_before_close():
    async def run():
        memory, jobs = FakeMemory(), FakeJobs()
        started, finish = threading.Event(), threading.Event()
        def remember(player_id, inputs):
            started.set()
            assert finish.wait(5)
            assert not memory.closed
        memory.remember = remember
        batch = MemoryBatch("player", (("game", "request", "preference"),))
        jobs.batches.append(batch)
        service = PlayerMemoryService(memory, jobs, True, FakeTelemetry(), OperationSupervisor())
        worker = asyncio.create_task(service.run_worker())
        try:
            assert await asyncio.to_thread(started.wait, 5)
            worker.cancel()
            await asyncio.sleep(0)
            assert not worker.done()
        finally:
            finish.set()
            with pytest.raises(asyncio.CancelledError):
                await worker
        assert jobs.completed == [batch]
        service.close()
        assert memory.closed
    asyncio.run(run())


def test_missing_provider_disables_worker_and_collection():
    async def run():
        jobs = FakeJobs()
        service = PlayerMemoryService(None, jobs, True, FakeTelemetry(), OperationSupervisor())
        assert (await service.status("player"))["available"] is False
        assert await service.preferences_for("player") == ()
        service.queue_input("player", "game", "request", "a long preference input")
        assert jobs.inputs == []
        await service.run_worker()
        with pytest.raises(ValueError):
            await service.clear("player")
        service.close()
    asyncio.run(run())


def test_idle_worker_stop_is_explicit_and_prompt():
    async def run():
        service = PlayerMemoryService(FakeMemory(), FakeJobs(), True, FakeTelemetry(), OperationSupervisor())
        worker = asyncio.create_task(service.run_worker())
        try:
            service.request_stop()
            await asyncio.wait_for(worker, 0.5)
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
    asyncio.run(run())


def test_repeated_worker_cancellation_preserves_real_batch_and_close_guard():
    async def run():
        memory, jobs = FakeMemory(), FakeJobs()
        started, finish = threading.Event(), threading.Event()
        def remember(*args):
            started.set()
            assert finish.wait(5)
            assert not memory.closed
        memory.remember = remember
        batch = MemoryBatch("player", (("game", "request", "preference"),))
        jobs.batches.append(batch)
        service = PlayerMemoryService(memory, jobs, True, FakeTelemetry(), OperationSupervisor())
        worker = asyncio.create_task(service.run_worker())
        try:
            assert await asyncio.to_thread(started.wait, 2)
            worker.cancel()
            await asyncio.sleep(0)
            worker.cancel()
            await asyncio.sleep(0.01)
            assert not worker.done()
            with pytest.raises(RuntimeError, match="active"):
                service.close()
        finally:
            finish.set()
            await asyncio.gather(worker, return_exceptions=True)
        assert jobs.completed == [batch]
        service.close()
        assert memory.closed
    asyncio.run(run())
