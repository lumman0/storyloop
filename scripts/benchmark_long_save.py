"""Bounded, offline read benchmark using temporary synthetic SQLite saves.

Requires this checkout's existing agents dependencies. Never reads configuration,
DATABASE_URL, player saves or model credentials; no model/client is instantiated.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import gc
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
# A directly invoked script must benchmark this checkout rather than another
# editable installation sharing the same package name.
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import event, inspect, text
from sqlalchemy.exc import OperationalError

from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_harness.agents.scene_turn import SceneContextProjector
from storyloop_harness.world.scenario import ScenarioPackage
from storyloop_harness.world.worldbook import Worldbook, WorldbookEntry

ACTORS = ("dockhand", "vendor", "guide")
GAME = "synthetic-benchmark"
QUERY = "Guide, tell me what happened to the missing cargo."


def synthetic_package() -> ScenarioPackage:
    base = ScenarioPackage.load(ROOT / "examples/freeform")
    state = deepcopy(base.initial_state)
    names = {actor: actor.title() for actor in ACTORS}
    for actor in ACTORS:
        state["actors"][actor] = {"location": "harbor_square"}
    cards = tuple((actor, f"{actor}_card") for actor in ACTORS)
    book = Worldbook(base.package_id, base.version, [
        WorldbookEntry(card, f"{names[actor]} is a harbor worker. " * 8,
                       "actor", frozenset({actor}), "card")
        for actor, card in cards
    ])
    return replace(base, initial_state=state, actor_cards=cards, actor_names=names,
                   worldbook=book, initial_work=(), story_blueprint=None)


def seed_history(store: SQLiteGameStore, package: ScenarioPackage, turns: int) -> None:
    """Bulk fixture insertion, not a measurement of runtime commit throughput."""
    package.seed_game(store, GAME)
    with store.engine.begin() as db:
        for start in range(1, turns + 1, 250):
            events, observations = [], []
            for turn in range(start, min(start + 250, turns + 1)):
                input_id = f"turn-{turn:05}:input"
                message = f"Turn {turn}: check the missing cargo with the harbor workers. " * 3
                events.append({"id": input_id, "kind": "player_input", "actor": "player",
                               "cause": None, "tick": turn, "version": turn * 4 - 3,
                               "details": json.dumps({"text": message, "channel": "speech",
                                                      "target_ids": list(ACTORS)})})
                observations.append({"id": f"{input_id}:scene", "event": input_id,
                                     "recipient": "player", "channel": "scene", "tick": turn,
                                     "content": f"The harbor workers inspect the cargo at turn {turn}. " * 4})
                for index, actor in enumerate(ACTORS):
                    speech = f"{actor.title()} reports a public cargo detail from turn {turn}. " * 3
                    reply_id = f"turn-{turn:05}:reply:{actor}"
                    events.append({"id": reply_id, "kind": "npc_spoke", "actor": actor,
                                   "cause": input_id, "tick": turn, "version": turn * 4 - 2 + index,
                                   "details": json.dumps({"player_message": message, "speech": speech})})
                    observations.extend([
                        {"id": f"{input_id}:heard:{actor}", "event": input_id,
                         "recipient": actor, "channel": "speech", "tick": turn, "content": message},
                        {"id": f"{reply_id}:player", "event": reply_id,
                         "recipient": "player", "channel": "dialogue", "tick": turn, "content": speech},
                    ])
            db.execute(text("""INSERT INTO events
                (game_id,event_id,kind,actor_id,cause_id,tick,effects,details,state_version)
                VALUES ('synthetic-benchmark',:id,:kind,:actor,:cause,:tick,'[]',:details,:version)"""), events)
            for order, row in enumerate(observations, start=(start - 1) * 7):
                row["order"] = order
            db.execute(text("""INSERT INTO observations
                (game_id,observation_id,event_id,recipient_id,channel,content,tick,created_order)
                VALUES ('synthetic-benchmark',:id,:event,:recipient,:channel,:content,:tick,:order)"""), observations)
        db.execute(text("UPDATE games SET version=:version,tick=:tick WHERE game_id=:game"),
                   {"version": turns * 4, "tick": turns, "game": GAME})


def measure(store: SQLiteGameStore, operation, summarize, repeats: int, timeout: int) -> dict:
    queries = [0]
    deadline = [0.0]
    expired = [False]

    def interrupt_if_expired():
        expired[0] = time.perf_counter() >= deadline[0]
        return int(expired[0])

    def count_query(connection, *_args):
        queries[0] += 1
        connection.connection.driver_connection.set_progress_handler(interrupt_if_expired, 10000)

    event.listen(store.engine, "before_cursor_execute", count_query)
    samples = []
    summary = None
    try:
        for _ in range(repeats):
            gc.collect()
            queries[0] = 0
            expired[0] = False
            tracemalloc.start()
            started = time.perf_counter()
            deadline[0] = started + timeout
            status = "ok"
            try:
                result = operation()
            except OperationalError as cause:
                if not expired[0] or str(cause.orig) != "interrupted":
                    raise
                status = "sql_timeout"
            finally:
                elapsed = (time.perf_counter() - started) * 1000
                peak = tracemalloc.get_traced_memory()[1]
                tracemalloc.stop()
            samples.append({"elapsed_ms": round(elapsed, 3),
                            "python_peak_mib": round(peak / (1024 * 1024), 3),
                            "sql_statements": queries[0], "status": status})
            if status != "ok":
                break  # Repeating an expensive interrupted query adds no baseline evidence.
            summary = summarize(result)
            del result
    finally:
        event.remove(store.engine, "before_cursor_execute", count_query)
    timed_out = any(row["status"] != "ok" for row in samples)
    return {"status": "sql_timeout" if timed_out else "ok",
            "median_ms": None if timed_out else round(statistics.median(row["elapsed_ms"] for row in samples), 3),
            "max_python_peak_mib": max(row["python_peak_mib"] for row in samples),
            "samples": samples, "result": None if timed_out else summary}


def context_summary(context) -> dict:
    request = context.request
    rows = [len(item["own_history"]) for item in request["npc_contexts"]]
    if len(request["player_history"]) > 14 or any(count > 11 for count in rows):
        raise AssertionError("projected history exceeded the current output bounds")
    return {"player_history_entries": len(request["player_history"]),
            "npc_history_entries": rows, "responders": list(context.focus_actor_ids),
            "request_utf8_bytes": len(json.dumps(request, ensure_ascii=False).encode("utf-8"))}


def observation_query_plan(store: SQLiteGameStore) -> list[str]:
    """Inspect the current actor-history join; excluded from measured queries."""
    with store.engine.connect() as db:
        return [row[3] for row in db.execute(text("""EXPLAIN QUERY PLAN
            SELECT o.observation_id,o.event_id,o.channel,o.content,o.tick,o.created_order,e.state_version
            FROM observations AS o JOIN events AS e
            ON e.game_id=o.game_id AND e.event_id=o.event_id
            WHERE o.game_id=:game AND o.recipient_id='player' AND e.state_version>-1
            ORDER BY e.state_version,o.created_order,o.observation_id"""), {"game": GAME})]


def git_value(arguments: list[str]) -> str | None:
    try:
        return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}",
                               "-C", str(ROOT), *arguments], check=True,
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", nargs="+", type=int, choices=(100, 1000, 10000),
                        default=[100, 1000, 10000])
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=3)
    parser.add_argument("--sql-timeout-seconds", type=int, choices=range(1, 31), default=10,
                        help="SQLite work budget per operation; interrupted samples are reported")
    parser.add_argument("--experimental-observation-index", action="store_true",
                        help="Add an event/recipient index only in the temporary benchmark database")
    args = parser.parse_args(argv)
    if len(set(args.turns)) != len(args.turns):
        parser.error("turn counts must not repeat")
    git_status = git_value(["status", "--porcelain"])
    report = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(), "environment": {
        "python": platform.python_version(), "interpreter": sys.executable,
        "platform": platform.platform(), "cpu": platform.processor(),
        "sqlite": sqlite3.sqlite_version, "sqlalchemy": version("SQLAlchemy"),
        "agentscope": version("agentscope"), "git_sha": git_value(["rev-parse", "HEAD"]),
        "working_tree_dirty": None if git_status is None else bool(git_status),
        "read_module_sha256": {
            name: hashlib.sha256(Path(sys.modules[name].__file__).read_bytes()).hexdigest()
            for name in ("storyloop_platform.adapters.sql_store", "storyloop_harness.agents.scene_turn")
        },
    }, "method": {"repeats": args.repeats, "actors": len(ACTORS), "events_per_turn": 4,
                    "observations_per_turn": 7, "compression_checkpoints": 0,
                    "sql_timeout_seconds": args.sql_timeout_seconds,
                    "experimental_observation_index": args.experimental_observation_index,
                    "memory": "tracemalloc Python allocations; excludes native SQLite/RSS",
                    "cache": "OS cache not flushed; no separate warm-up; fresh DB per size",
                    "timing": "read operation only; snapshot load, seeding and imports excluded"},
              "results": []}
    package = synthetic_package()
    for turns in args.turns:
        print(f"Benchmarking {turns} synthetic turns...", file=sys.stderr, flush=True)
        with tempfile.TemporaryDirectory(prefix="storyloop-benchmark-") as directory:
            path = Path(directory) / "synthetic.sqlite3"
            store = SQLiteGameStore(str(path))
            try:
                seed_history(store, package, turns)
                added_index = False
                if args.experimental_observation_index:
                    existing = inspect(store.engine).get_indexes("observations")
                    if not any(row["column_names"] == ["game_id", "event_id", "recipient_id"] for row in existing):
                        with store.engine.begin() as db:
                            db.execute(text("""CREATE INDEX benchmark_observations_event_recipient
                                ON observations (game_id,event_id,recipient_id)"""))
                        added_index = True
                snapshot = store.load(GAME)
                projector = SceneContextProjector(store, package)
                point = {"turns": turns, "events": turns * 4, "observations": turns * 7,
                         "database_mib": round(path.stat().st_size / (1024 * 1024), 3),
                         "observation_indexes": [{"name": row["name"], "columns": row["column_names"]}
                                                 for row in inspect(store.engine).get_indexes("observations")],
                         "experimental_index_added": added_index,
                         "actor_history_query_plan": observation_query_plan(store)}
                operations = {
                    "context_projection": (lambda: projector.project(snapshot, QUERY), context_summary),
                    "player_visible_history": (lambda: store.observations_for(GAME, "player"), len),
                    "player_input_history": (lambda: store.player_inputs_for(GAME), len),
                    "player_agent_history": (lambda: store.agent_context_entries(GAME, "player"), len),
                }
                for name, (operation, summarize) in operations.items():
                    point[name] = measure(store, operation, summarize, args.repeats, args.sql_timeout_seconds)
                for name, expected in (("player_visible_history", turns * 4),
                                       ("player_input_history", turns), ("player_agent_history", turns * 5)):
                    if point[name]["status"] == "ok" and point[name]["result"] != expected:
                        raise AssertionError("synthetic history read counts do not match fixture")
                report["results"].append(point)
            finally:
                store.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
