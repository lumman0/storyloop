"""Play a scheduled campaign with ReAct dialogue and explicit player choices."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

from story_harness.adapters.runtime_config import HarnessConfig
from story_harness.adapters.telemetry import configured_telemetry
from story_harness.agents.scene_narrator import CampaignSceneNarrator
from story_harness.agents.novel_narrator import NovelTurnNarrator
from story_harness.agents.heart_message_writer import NpcHeartMessageWriter
from story_harness.agents.action_advisor import ActionOptionAdvisor
from story_harness.cli.react_play import DEFAULT_CONFIG
from story_harness.cli.guidance_view import format_turn_output
from story_harness.runtime.campaign import CampaignProgram, CampaignSession
from story_harness.runtime.guidance import GuidanceAdvisor
from story_harness.runtime.react_factory import make_react_session
from story_harness.runtime.story_clock import StoryClock
from story_harness.world.scenario import ScenarioPackage


async def play(package_path: str, config_path: str, game_id: str, db_path: str | None = None) -> None:
    root = Path(package_path)
    package = ScenarioPackage.load(root)
    program = CampaignProgram.load(root / "campaign.json")
    if program.program_id != package.package_id or program.ticks_per_day != package.ticks_per_day:
        raise ValueError("campaign schedule does not match scenario")
    config = HarnessConfig.load(config_path)
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
    turns_per_story_tick = max(1, *(step.get("at_subtick", 0) + 1 for step in program.steps))
    clock = (StoryClock(program.ticks_per_day * turns_per_story_tick,
                        overnight_requires_rest=True)
             if turns_per_story_tick > 1 else None)
    react = make_react_session(config, package, store, values, telemetry, story_clock=clock)
    session = CampaignSession(
        store, program, react, telemetry=telemetry,
        turns_per_story_tick=turns_per_story_tick,
        scene_presenter=CampaignSceneNarrator(
            package, program, config.create_model("narration", values, telemetry), telemetry,
        ) if package.presentation_mode == "interactive" else None,
        novel_presenter=(NovelTurnNarrator(
            package, config.create_model("narration", values, telemetry), telemetry,
        ) if package.presentation_mode == "novel" else None),
        message_writer=NpcHeartMessageWriter(react.npc_pool, package.role_cards),
    )
    advisor = GuidanceAdvisor(store, package, program, telemetry=telemetry)
    option_task = ("followup_actions" if "followup_actions" in config.task_models
                   else "npc_selection")
    option_advisor = ActionOptionAdvisor(
        config.create_model(option_task, values, telemetry), telemetry,
        config.runtime.followup_timeout_seconds,
    )
    print(f"{package.package_id} | game={game_id} | /next 推进时段 | /quit 退出")
    if new_game and package.opening:
        print(package.opening)
    try:
        pending_id = f"campaign-turn-{store.completed_turn_count(game_id)}"
        recovered = await session.recover_turn(game_id, pending_id)
        initial = recovered or await session.start(game_id)
        if not new_game and recovered is None:
            previous_index = store.completed_turn_count(game_id) - 1
            if previous_index >= 0:
                previous = store.event_details(game_id, f"campaign-turn-{previous_index}:completed") or {}
                prior_text = previous.get("display_text")
                if isinstance(prior_text, str) and prior_text and prior_text != initial.text:
                    print("[上次回合回放]")
                    print(prior_text)
        guidance = await advisor.advise(game_id, initial.snapshot,
                                        gate_id=initial.gate_id, complete=initial.complete,
                                        visible_text=initial.text)
        print(format_turn_output(initial.text,
                                 f"[第 {initial.snapshot.data['campaign']['day']} 天 | tick {initial.snapshot.tick}]",
                                 guidance))
        options = (await option_advisor.suggest(initial.text or package.opening,
                                                package.presentation_mode,
                                                game_id, package.package_id)
                   if initial.gate_id is None and not initial.complete else ())
        if options:
            print("\n".join(f"{index}. {option.label}" for index, option in enumerate(options, 1)))
        while not initial.complete:
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
            turn_id = f"campaign-turn-{store.completed_turn_count(game_id)}"
            try:
                outcome = await session.submit(game_id, player_text, turn_id)
            except ValueError as error:
                print(f"[输入未生效] {error}")
                continue
            guidance = await advisor.advise(game_id, outcome.snapshot,
                                            gate_id=outcome.gate_id, complete=outcome.complete,
                                            visible_text=outcome.text)
            print(format_turn_output(outcome.text,
                                     f"[第 {outcome.snapshot.data['campaign']['day']} 天 | tick {outcome.snapshot.tick}]",
                                     guidance))
            options = (await option_advisor.suggest(outcome.text, package.presentation_mode,
                                                    game_id, package.package_id)
                       if outcome.gate_id is None and not outcome.complete else ())
            if options:
                print("\n".join(f"{index}. {option.label}" for index, option in enumerate(options, 1)))
            initial = outcome
    finally:
        telemetry.flush()
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="campaign scenario directory")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="versioned JSON model config")
    parser.add_argument("--db", help="SQLite game database")
    parser.add_argument("--game-id", default="campaign-local")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(play(args.package, args.config, args.game_id, args.db))


if __name__ == "__main__":
    main()
