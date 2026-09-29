"""Exercise player input, NPC isolation and background time without a model API."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from agentscope.model import ChatModelBase, ChatResponse

from story_harness.agents.npc_agent import NpcAgentPool
from story_harness.runtime.npc_work import make_npc_reply_handler
from story_harness.runtime.player_input import submit_player_input
from story_harness.runtime.runner import TurnRunner
from story_harness.world.scenario import ScenarioPackage
from story_harness.runtime.schedule import scenario_cue
from story_harness.adapters.store import SQLiteGameStore
from story_harness.adapters.telemetry import Telemetry, configured_telemetry


class OfflineReplyModel(ChatModelBase):
    """Deterministic test double; no simulated reasoning or world authority."""

    def __init__(self, actor_id: str) -> None:
        super().__init__(model_name=f"offline-{actor_id}", stream=False)
        self.actor_id = actor_id

    async def __call__(self, prompt: object, **kwargs: object) -> ChatResponse:
        return ChatResponse(content=[{"type": "text", "text": f"{self.actor_id}：我听到了。"}])


async def run_interaction_demo(
    path: str | Path, message: str = "你好，今天怎么样？", turns: int = 4,
    telemetry: Telemetry | None = None,
) -> dict[str, object]:
    if turns < 1:
        raise ValueError("turns must be positive")
    package = ScenarioPackage.load(path)
    actor_id = package.actor_cards[0][0]
    with TemporaryDirectory() as directory:
        store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
        package.seed_game(store, "demo-game")
        pool = NpcAgentPool(store, lambda game_id, actor: OfflineReplyModel(actor), telemetry=telemetry)
        runner = TurnRunner(
            store,
            {
                "npc_reply": make_npc_reply_handler(pool, package.role_cards, package.actor_names),
                "scenario_cue": scenario_cue,
            },
            max_steps=8,
            telemetry=telemetry,
        )
        actors = store.load("demo-game").data["actors"]
        channel = (
            "speech"
            if actors["player"]["location"] == actors[actor_id]["location"]
            else "private_message"
        )
        processed: list[str] = []
        for index in range(turns):
            submit_player_input(
                store, "demo-game", f"input-{index + 1}", message,
                (actor_id,), channel=channel,
            )
            result = await runner.run_async("demo-game")
            processed.extend(result.processed_work_ids)
        return {
            "scenario": package.package_id,
            "time": {"tick": result.snapshot.tick, "day": (
                result.snapshot.tick // package.ticks_per_day + 1
                if package.ticks_per_day is not None else None
            )},
            "player_inputs": [item.text for item in store.player_inputs_for("demo-game")],
            "npc_observations": [item.content for item in store.observations_for("demo-game", actor_id)],
            "player_heard": [item.content for item in store.observations_for("demo-game", "player")],
            "processed": processed,
            "state": result.snapshot.data,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package")
    parser.add_argument("--message", default="你好，今天怎么样？")
    parser.add_argument("--turns", type=int, default=4)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    telemetry = configured_telemetry()
    try:
        print(json.dumps(
            asyncio.run(run_interaction_demo(args.package, args.message, args.turns, telemetry)),
            ensure_ascii=False, indent=2,
        ))
    finally:
        telemetry.flush()


if __name__ == "__main__":
    main()
