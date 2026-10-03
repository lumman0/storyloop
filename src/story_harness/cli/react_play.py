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
from story_harness.agents.action_advisor import ActionOptionAdvisor
from story_harness.agents.novel_narrator import NovelTurnNarrator
from story_harness.cli.guidance_view import format_turn_output
from story_harness.runtime.guidance import GuidanceAdvisor
from story_harness.runtime.react_factory import make_react_session
from story_harness.runtime.novel_presentation import (
    present_freeform_novel, recover_last_freeform_novel,
)


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
    novel_presenter = (NovelTurnNarrator(
        package, config.create_model("narration", values, telemetry), telemetry,
    ) if package.presentation_mode == "novel" else None)
    option_task = ("followup_actions" if "followup_actions" in config.task_models
                   else "npc_selection")
    option_advisor = ActionOptionAdvisor(
        config.create_model(option_task, values, telemetry), telemetry,
        config.runtime.followup_timeout_seconds,
    )
    print(f"{package.package_id} | game={game_id} | /quit 退出")
    if new_game and package.opening:
        print(package.opening)
    options = (await option_advisor.suggest(package.opening, package.presentation_mode,
                                            game_id, package.package_id)
               if new_game and package.opening else ())
    if options:
        print("\n".join(f"{index}. {option.label}" for index, option in enumerate(options, 1)))
    try:
        if novel_presenter is not None and not new_game:
            prior_body = await recover_last_freeform_novel(
                store, package, novel_presenter, game_id, session.run_ready_work,
            )
            if prior_body is not None:
                print("[上次回合回放]")
                print(prior_body)
                options = await option_advisor.suggest(
                    prior_body, package.presentation_mode, game_id, package.package_id,
                )
                print("\n".join(f"{index}. {option.label}"
                                for index, option in enumerate(options, 1)))
        while True:
            try:
                player_text = input("你> ").strip()
            except EOFError:
                break
            if player_text == "/quit":
                break
            if not player_text:
                continue
            if player_text in {"1", "2", "3"} and options:
                player_text = options[int(player_text) - 1].input
            turn_id = uuid4().hex
            outcome = await session.run_turn(game_id, player_text, turn_id)
            body = outcome.narration
            if novel_presenter is not None:
                body, _ = await present_freeform_novel(
                    store, package, novel_presenter, game_id,
                    player_text, turn_id, outcome.segments,
                )
            guidance = await advisor.advise(game_id, outcome.snapshot,
                                            visible_text=body)
            if outcome.narration_fallback and novel_presenter is None:
                body += "\n[叙述模型出错，以上为已提交的可见结果]"
            print(format_turn_output(body, f"[tick {outcome.snapshot.tick} | turn {turn_id}]", guidance))
            options = await option_advisor.suggest(body, package.presentation_mode,
                                                   game_id, package.package_id)
            print("\n".join(f"{index}. {option.label}" for index, option in enumerate(options, 1)))
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
