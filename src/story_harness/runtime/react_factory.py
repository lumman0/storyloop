"""Shared wiring for the main/NPC ReAct session."""

from story_harness.adapters.runtime_config import HarnessConfig
from story_harness.adapters.store import GameStore
from story_harness.adapters.telemetry import Telemetry
from story_harness.agents.main_agent import MainReActAgent
from story_harness.agents.action_resolver import ModelActionResolver
from story_harness.agents.npc_agent import NpcAgentPool
from story_harness.agents.selector_agent import AgentScopeWorkSelector
from story_harness.runtime.game_session import GameSession
from story_harness.runtime.story_clock import StoryClock
from story_harness.world.scenario import ScenarioPackage


def make_react_session(config: HarnessConfig, package: ScenarioPackage,
                       store: GameStore, values: dict[str, str], telemetry: Telemetry,
                       story_clock: StoryClock | None = None) -> GameSession:
    pool = NpcAgentPool(
        store,
        lambda _game_id, _actor_id: config.create_model("npc_reply", values, telemetry),
        max_iters=config.runtime.npc_max_iters,
        worldbook=package.worldbook,
        telemetry=telemetry,
        story_clock=story_clock,
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
            story_clock=story_clock,
        ),
        pool,
        max_steps=config.runtime.max_steps,
        max_npc_replies=config.runtime.max_npc_replies,
        selector=AgentScopeWorkSelector(config.create_model("work_selection", values, telemetry), telemetry=telemetry),
        telemetry=telemetry,
        story_clock=story_clock,
        action_resolver=ModelActionResolver(
            store, package, config.create_model("adjudication", values, telemetry), telemetry,
        ),
    )
