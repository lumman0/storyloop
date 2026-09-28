"""Run every offline end-to-end validation with one command."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from story_harness.cli.demo import run_demo
from story_harness.cli.interaction_demo import run_interaction_demo


def run_all() -> dict[str, object]:
    examples = Path(__file__).resolve().parents[3] / "examples"
    window = run_demo()
    absent = run_demo(a_present=False)
    freeform = asyncio.run(run_interaction_demo(examples / "freeform"))
    scheduled = asyncio.run(run_interaction_demo(examples / "scheduled"))
    assert window["window_broken"] and window["A"] and window["B"] and not window["C"]
    assert not absent["A"] and not absent["B"] and not absent["C"]
    assert freeform["time"] == {"tick": 4, "day": 2}
    assert scheduled["time"] == {"tick": 4, "day": 2}
    assert "harbor-opening-cue" in freeform["processed"]
    assert "relay-shift-handoff" in scheduled["processed"]
    assert any("开市钟" in text for text in freeform["npc_observations"])
    assert any("交接班" in text for text in scheduled["npc_observations"])
    return {
        "result": "passed",
        "window": {"A": window["A"], "B": window["B"], "C": window["C"]},
        "freeform": {"day": freeform["time"]["day"], "phase": freeform["state"]["world"]["market_phase"]},
        "scheduled": {"day": scheduled["time"]["day"], "segment": scheduled["state"]["world"]["segment"]},
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run_all(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
