"""Terminal entry point for the complete main/NPC ReAct turn loop."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path
from uuid import uuid4

from story_harness.adapters.runtime_config import HarnessConfig
from story_harness.world.scenario import ScenarioPackage
from story_harness.adapters.telemetry import configured_telemetry
from story_harness.cli.guidance_view import format_turn_output
from story_harness.runtime.guidance import GuidanceAdvisor
from story_harness.runtime.react_factory import make_react_session


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "defaults" / "local.json"


async def play(
    package_path: str, config_path: str, game_id: str, db_path: str | None = None
) -> None:
    config = HarnessConfig.load(config_path)
    package = ScenarioPackage.load(package_path)
    values = dict(os.environ)
    if not config.model_api_key(values):
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
    advisor = GuidanceAdvisor(store, package, telemetry=telemetry)
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
            guidance = await advisor.advise(game_id, outcome.snapshot,
                                            visible_text=outcome.narration)
            body = outcome.narration
            if outcome.narration_fallback:
                body += "\n[叙述模型出错，以上为已提交的可见结果]"
            print(format_turn_output(body, f"[tick {outcome.snapshot.tick} | turn {turn_id}]", guidance))
    finally:
        telemetry.flush()
        store.close()


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
