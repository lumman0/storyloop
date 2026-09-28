"""Single-NPC terminal harness using a configured OpenAI-compatible model."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path
from uuid import uuid4

from story_harness.agents.npc_agent import NpcAgentPool
from story_harness.adapters.model_config import BailianModelRouter
from story_harness.runtime.npc_work import make_npc_reply_handler
from story_harness.runtime.player_input import submit_player_input
from story_harness.runtime.runner import TurnRunner
from story_harness.world.scenario import ScenarioPackage
from story_harness.runtime.schedule import scenario_cue
from story_harness.agents.selector_agent import AgentScopeWorkSelector
from story_harness.adapters.store import SQLiteGameStore
from story_harness.adapters.telemetry import configured_telemetry


async def play(package_path: str, db_path: str, game_id: str, actor_id: str | None) -> None:
    package = ScenarioPackage.load(package_path)
    values = dict(os.environ)
    if not (values.get("STORY_BAILIAN_API_KEY") or values.get("STORY_NPC_API_KEY")):
        values["STORY_BAILIAN_API_KEY"] = getpass.getpass("百炼 API Key（输入不回显）: ")
    model_router = BailianModelRouter.from_environment(values)
    selected_actor = actor_id or package.actor_cards[0][0]
    if selected_actor not in package.role_cards:
        raise ValueError(f"actor {selected_actor!r} is not in this package")
    store = SQLiteGameStore(db_path)
    try:
        snapshot = store.load(game_id)
    except KeyError:
        package.seed_game(store, game_id)
        snapshot = store.load(game_id)
    if snapshot.data.get("scenario", {}).get("id") != package.package_id or snapshot.data["scenario"].get("version") != package.version:
        raise ValueError("saved game belongs to a different scenario version")

    pool = NpcAgentPool(store, lambda _game_id, _actor_id: model_router.create_model("npc_reply"))
    runner = TurnRunner(
        store,
        {
            "npc_reply": make_npc_reply_handler(pool, package.role_cards),
            "scenario_cue": scenario_cue,
        },
        max_steps=8,
        selector=AgentScopeWorkSelector(model_router.create_model("work_selection")),
        telemetry=configured_telemetry(),
    )
    print(f"{package.package_id} | game={game_id} | NPC={selected_actor} | /quit 退出")
    while True:
        try:
            message = input("你> ").strip()
        except EOFError:
            break
        if message == "/quit":
            break
        if not message:
            continue
        before = store.load(game_id)
        actors = before.data["actors"]
        channel = (
            "speech"
            if actors["player"]["location"] == actors[selected_actor]["location"]
            else "private_message"
        )
        seen = {item.observation_id for item in store.observations_for(game_id, "player")}
        submit_player_input(store, game_id, uuid4().hex, message, (selected_actor,), channel=channel)
        result = await runner.run_async(game_id)
        for observation in store.observations_for(game_id, "player"):
            if observation.observation_id not in seen:
                print(f"{observation.channel}> {observation.content}")
        print(f"[tick {result.snapshot.tick}]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="scenario package directory")
    parser.add_argument("--db", default=str(Path.cwd() / "story-game.sqlite3"))
    parser.add_argument("--game-id", default="local-game")
    parser.add_argument("--actor-id")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(play(args.package, args.db, args.game_id, args.actor_id))


if __name__ == "__main__":
    main()
