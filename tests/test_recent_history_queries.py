"""Recent-history SQL preserves ordering and ownership without loading all rows."""

from pathlib import Path

import pytest
from sqlalchemy import event, text

from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_harness.core.contracts import Observation, WorldEvent
from storyloop_harness.world.scenario import ScenarioPackage


@pytest.fixture
def history_store(tmp_path):
    store = SQLiteGameStore(str(tmp_path / "history.sqlite3"))
    package = ScenarioPackage.load(Path(__file__).resolve().parents[1] / "examples/freeform")
    package.seed_game(store, "game")
    for index in range(12):
        snapshot = store.load("game")
        event_id = f"turn-{index}"
        store.commit("game", snapshot.version,
            WorldEvent(event_id, "player_input", "player", None, index, (),
                       {"text": f"action {index}", "target_ids": ["dockhand"]}),
            tuple(Observation(f"{event_id}-{suffix}", event_id, actor, "scene", f"{index}-{suffix}", index)
                  for suffix, actor in [("a", "player"), ("b", "player"), ("private", "dockhand")]), ())
    try:
        yield store
    finally:
        store.engine.dispose()


def test_recent_limits_are_applied_in_sql_and_match_original_tail(history_store):
    store = history_store
    expected_inputs = store.player_inputs_for("game")[-4:]
    expected_observations = store.observations_for("game", "player")[-3:]
    queries = []
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        queries.append(statement)
    event.listen(store.engine, "before_cursor_execute", record)
    try:
        assert store.player_inputs_for("game", limit=4) == expected_inputs
        assert store.observations_for("game", "player", limit=3) == expected_observations
    finally:
        event.remove(store.engine, "before_cursor_execute", record)
    assert len(queries) == 2 and all("LIMIT" in query.upper() for query in queries)
    assert all(item.recipient_id == "player" for item in expected_observations)
    assert store.player_inputs_for("missing", limit=4) == []


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_limits_cannot_accidentally_remove_sql_bound(history_store, limit):
    with pytest.raises(ValueError):
        history_store.player_inputs_for("game", limit=limit)
    with pytest.raises(ValueError):
        history_store.observations_for("game", "player", limit=limit)


def test_context_join_does_not_rescan_all_observations_per_event(history_store):
    store = history_store
    with store.engine.begin() as db:
        db.execute(text("""INSERT INTO events
            (game_id,event_id,kind,actor_id,cause_id,tick,effects,details,state_version)
            VALUES ('game',:id,'player_input','player',NULL,:version,'[]','{"text":"hello"}',:version)"""),
            [{"id": f"bulk-{i}", "version": i + 100} for i in range(1000)])
        db.execute(text("""INSERT INTO observations
            (game_id,observation_id,event_id,recipient_id,channel,content,tick,created_order)
            VALUES ('game',:id,:id,'player','scene','visible',:version,:version)"""),
            [{"id": f"bulk-{i}", "version": i + 100} for i in range(1000)])
    steps = 0
    def connected(connection, _record):
        def progress():
            nonlocal steps
            steps += 1000
            return int(steps > 1_000_000)
        connection.set_progress_handler(progress, 1000)
    event.listen(store.engine, "connect", connected)
    try:
        rows = store.agent_context_entries("game", "player")
        assert len(rows) >= 2000
    finally:
        event.remove(store.engine, "connect", connected)
