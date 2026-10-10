"""Durable extraction retries retain a terminal history after exhaustion."""

from pathlib import Path

import pytest
from sqlalchemy import text

from storyloop_platform.adapters.sql_database import open_database, sqlite_url, upgrade_database
from storyloop_platform.memory.jobs import SQLPlayerMemoryJobs


@pytest.fixture
def jobs(tmp_path: Path, monkeypatch):
    clock = [100000]
    monkeypatch.setattr("storyloop_platform.memory.jobs.time.time", lambda: clock[0])
    url = sqlite_url(str(tmp_path / "memory.sqlite3"))
    upgrade_database(url)
    engine = open_database(url)
    store = SQLPlayerMemoryJobs(engine)
    store.set_enabled("player", True)
    for index in range(6):
        assert store.enqueue("player", "game", str(index), "I prefer stories with slower pacing.")
    try:
        yield store, clock
    finally:
        engine.dispose()


def rows(jobs):
    with jobs.engine.connect() as db:
        return db.execute(text("SELECT status,attempt_count FROM player_memory_inputs")).all()


@pytest.mark.parametrize("cleanup", ["clear", "opt_out"])
def test_expired_third_claim_becomes_failed_and_can_be_removed(jobs, cleanup):
    store, clock = jobs
    batches = []
    for now in (100000, 100301, 100602):
        clock[0] = now
        batch = store.claim()
        assert batch is not None
        batches.append(batch)
    assert batches[0] == batches[1] == batches[2]
    clock[0] = 100901
    assert store.claim() is None
    assert rows(store) == [("processing", 3)] * 6
    assert store.pending_count("player") == 6
    clock[0] = 100903
    assert store.claim() is None
    assert store.pending_count("player") == 0
    assert rows(store) == [("failed", 3)] * 6
    if cleanup == "clear":
        store.clear("player")
    else:
        store.set_enabled("player", False)
    assert rows(store) == []


def test_third_failure_retains_failed_history(jobs):
    store, clock = jobs
    for now in (100000, 100121, 100242):
        clock[0] = now
        batch = store.claim()
        assert batch is not None
        store.fail(batch)
    assert store.pending_count("player") == 0
    assert rows(store) == [("failed", 3)] * 6
    clock[0] = 100903
    assert store.claim() is None
