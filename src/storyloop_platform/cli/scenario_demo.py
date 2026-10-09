"""Run the deterministic slice of a scenario package from the command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from storyloop_harness.advanced import TurnRunner
from storyloop_harness import ScenarioPackage
from storyloop_harness.advanced import advance_time, scenario_cue
from storyloop_platform.adapters.store import SQLiteGameStore


def run_package(path: str | Path, tick: int) -> dict[str, object]:
    if tick < 0:
        raise ValueError("tick must be nonnegative")
    package = ScenarioPackage.load(path)
    with TemporaryDirectory() as directory:
        store = SQLiteGameStore(str(Path(directory) / "scenario.sqlite3"))
        package.seed_game(store, "sample-game")
        if tick > 0:
            advance_time(store, "sample-game", tick, "sample-clock-advance")
        result = TurnRunner(
            store, {"scenario_cue": scenario_cue}, max_steps=20
        ).run("sample-game")
        return {
            "scenario": package.package_id,
            "version": package.version,
            "tick": result.snapshot.tick,
            "processed": list(result.processed_work_ids),
            "remaining": list(result.remaining_work_ids),
            "state": result.snapshot.data,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="directory containing manifest.json")
    parser.add_argument("--tick", type=int, default=1, help="logical time to reach")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run_package(args.package, args.tick), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
