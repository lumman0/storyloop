"""Shared wiring for the main/NPC ReAct session."""

from storyloop_platform.adapters.runtime_config import HarnessConfig
from storyloop_platform.adapters.store import GameStore
from storyloop_platform.adapters.telemetry import Telemetry
from storyloop_platform.legacy.main_agent import MainReActAgent
from storyloop_platform.legacy.action_resolver import ModelActionResolver
from storyloop_platform.legacy.npc_agent import NpcAgentPool
from storyloop_platform.legacy.selector_agent import AgentScopeWorkSelector
from storyloop_platform.runtime.game_session import GameSession
from storyloop_harness.advanced import StoryClock
from storyloop_harness import ScenarioPackage


def make_react_session(config: HarnessConfig, package: ScenarioPackage,
                       store: GameStore, values: dict[str, str], telemetry: Telemetry,
                       story_clock: StoryClock | None = None, *,
                       temperature: float | None = None,
                       context_window_tokens: int | None = None) -> GameSession:
    compression_task = ("context_compression" if "context_compression" in config.task_models
                        else "main_react")
    def model(task: str):
        return config.create_model(task, values, telemetry, temperature=temperature)

    pool = NpcAgentPool(
        store,
        lambda _game_id, _actor_id: model("npc_reply"),
        max_iters=config.runtime.npc_max_iters,
        worldbook=package.worldbook,
        telemetry=telemetry,
        story_clock=story_clock,
        context_window_tokens=min(config.context_window_for("npc_reply"),
                                  config.context_window_for(compression_task),
                                  context_window_tokens or config.context_window_for("npc_reply")),
        compression_model=model(compression_task),
    )
    return GameSession(
        store,
        package,
        lambda active_game_id: MainReActAgent(
            active_game_id,
            store,
            package.worldbook,
            model("main_react"),
            max_iters=config.runtime.main_max_iters,
            action_rules=package.action_rules,
            narration_model=model("narration"),
            telemetry=telemetry,
            opening=package.opening,
            story_clock=story_clock,
            context_window_tokens=min(config.context_window_for("main_react"),
                                      config.context_window_for(compression_task),
                                      context_window_tokens or config.context_window_for("main_react")),
            compression_model=model(compression_task),
            status_fields=package.status_fields,
        ),
        pool,
        max_steps=config.runtime.max_steps,
        max_npc_replies=config.runtime.max_npc_replies,
        selector=AgentScopeWorkSelector(model("work_selection"), telemetry=telemetry),
        telemetry=telemetry,
        story_clock=story_clock,
        action_resolver=ModelActionResolver(
            store, package, model("adjudication"), telemetry,
        ),
    )
