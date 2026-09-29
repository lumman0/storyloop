"""Terminal entry point for the complete main/NPC ReAct turn loop."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path
from uuid import uuid4

from story_harness.agents.npc_agent import NpcAgentPool
from story_harness.runtime.game_session import GameSession
from story_harness.agents.main_agent import MainReActAgent
from story_harness.adapters.runtime_config import HarnessConfig
from story_harness.world.scenario import ScenarioPackage
from story_harness.agents.selector_agent import AgentScopeWorkSelector
from story_harness.adapters.telemetry import configured_telemetry


DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "config" / "bailian-token-plan.json"


def make_react_session(config, package, store, values, telemetry):
    """Wire the shared ReAct loop for terminal modes."""
    pool = NpcAgentPool(
        store,
        lambda _game_id, _actor_id: config.create_model("npc_reply", values, telemetry),
        max_iters=config.runtime.npc_max_iters,
        worldbook=package.worldbook,
        telemetry=telemetry,
    )
    return GameSession(
        store,
        package,
        lambda active_game_id: MainReActAgent(
            active_game_id,
            store,
            package.worldbook,
            config.create_model("main_react", values, telemetry),
            max_iters=config.runtime.main_max_iters,
            action_rules=package.action_rules,
            narration_model=config.create_model("narration", values, telemetry),
            telemetry=telemetry,
            opening=package.opening,
        ),
        pool,
        max_steps=config.runtime.max_steps,
        max_npc_replies=config.runtime.max_npc_replies,
        selector=AgentScopeWorkSelector(config.create_model("work_selection", values, telemetry), telemetry=telemetry),
        telemetry=telemetry,
    )


async def play(
    package_path: str, config_path: str, game_id: str, db_path: str | None = None
) -> None:
    config = HarnessConfig.load(config_path)
    package = ScenarioPackage.load(package_path)
    values = dict(os.environ)
    if not values.get(config.api_key_env):
        values[config.api_key_env] = getpass.getpass("模型 API Key（输入不回显）: ")
    telemetry = configured_telemetry()
    store = config.create_store(db_path)
    new_game = False
    try:
        store.load(game_id)
    except KeyError:
        package.seed_game(store, game_id)
        new_game = True

    session = make_react_session(config, package, store, values, telemetry)
    print(f"{package.package_id} | game={game_id} | /quit 退出")
    if new_game and package.opening:
        print(package.opening)
    try:
        while True:
            try:
                player_text = input("你> ").strip()
            except EOFError:
                break
            if player_text == "/quit":
                break
            if not player_text:
                continue
            turn_id = uuid4().hex
            outcome = await session.run_turn(game_id, player_text, turn_id)
            print(outcome.narration)
            if outcome.narration_fallback:
                print("[叙述模型出错，以上为已提交的可见结果]")
            print(f"[tick {outcome.snapshot.tick} | turn {turn_id}]")
    finally:
        telemetry.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="scenario package directory")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="versioned JSON config")
    parser.add_argument("--db", help="override configured SQLite path")
    parser.add_argument("--game-id", default="local-game")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(play(args.package, args.config, args.game_id, args.db))


if __name__ == "__main__":
    main()
