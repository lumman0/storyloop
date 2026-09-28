"""Coordinate main ReAct decisions with the event-authoritative game runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from story_harness.core.actions import adjudicate_action
from story_harness.agents.npc_agent import NpcAgentPool
from story_harness.core.contracts import Observation, Snapshot, WorldEvent
from story_harness.agents.main_agent import MainDecision
from story_harness.runtime.npc_work import make_npc_reply_handler
from story_harness.core.perception import physical_observations
from story_harness.runtime.runner import TurnRunner, WorkSelector
from story_harness.world.scenario import ScenarioPackage
from story_harness.runtime.schedule import scenario_cue
from story_harness.adapters.store import GameStore
from story_harness.adapters.telemetry import Telemetry


class MainAgent(Protocol):
    async def decide(self, player_text: str) -> MainDecision: ...

    async def summarize(self, player_text: str, visible_results: list[str]) -> str: ...


@dataclass(frozen=True)
class TurnOutcome:
    decision: MainDecision
    narration: str
    player_observations: tuple[Observation, ...]
    processed_work_ids: tuple[str, ...]
    snapshot: Snapshot
    narration_fallback: bool = False


class GameSession:
    def __init__(
        self,
        store: GameStore,
        package: ScenarioPackage,
        main_factory: Callable[[str], MainAgent],
        npc_pool: NpcAgentPool,
        max_steps: int,
        selector: WorkSelector | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.store = store
        self.package = package
        self.main_factory = main_factory
        self.npc_pool = npc_pool
        self.max_steps = max_steps
        self.selector = selector
        self.telemetry = telemetry
        self._main: dict[str, MainAgent] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def run_turn(self, game_id: str, player_text: str, turn_id: str) -> TurnOutcome:
        if not player_text.strip() or not turn_id:
            raise ValueError("turn requires text and an ID")
        lock = self._locks.setdefault(game_id, asyncio.Lock())
        async with lock:
            before = self.store.load(game_id)
            scenario = before.data.get("scenario", {})
            if (
                scenario.get("id") != self.package.package_id
                or scenario.get("version") != self.package.version
            ):
                raise ValueError("game belongs to another scenario")
            visible_before = {
                item.observation_id for item in self.store.observations_for(game_id, "player")
            }
            if game_id not in self._main:
                self._main[game_id] = self.main_factory(game_id)
            main = self._main[game_id]
            decision = await main.decide(player_text)
            if decision.intent == "speech":
                self.store_input(game_id, turn_id, player_text, decision)
            elif decision.intent == "inspect":
                self._inspect(before, turn_id, player_text, decision)
            elif decision.intent == "action":
                self._act(before, turn_id, player_text, decision)
            else:
                raise ValueError(f"unsupported main intent: {decision.intent}")

            runner = TurnRunner(
                self.store,
                {
                    "npc_reply": make_npc_reply_handler(self.npc_pool, self.package.role_cards),
                    "scenario_cue": scenario_cue,
                },
                max_steps=self.max_steps,
                selector=self.selector,
                telemetry=self.telemetry,
            )
            result = await runner.run_async(game_id)
            new_observations = tuple(
                item for item in self.store.observations_for(game_id, "player")
                if item.observation_id not in visible_before
            )
            visible_results = [item.content for item in new_observations]
            try:
                narration = await main.summarize(player_text, visible_results)
                narration_fallback = False
            except Exception:
                narration = "\n".join(visible_results) if visible_results else "暂时没有可见变化。"
                narration_fallback = True
            return TurnOutcome(
                decision, narration, new_observations,
                result.processed_work_ids, result.snapshot, narration_fallback,
            )

    def store_input(
        self, game_id: str, turn_id: str, text: str, decision: MainDecision
    ) -> None:
        from story_harness.runtime.player_input import submit_player_input

        if any(actor_id not in self.package.role_cards for actor_id in decision.target_ids):
            raise ValueError("main agent selected an actor outside this scenario")
        submit_player_input(
            self.store, game_id, f"{turn_id}:input", text,
            tuple(decision.target_ids), channel=decision.channel,
        )

    def _inspect(
        self, before: Snapshot, turn_id: str, text: str, decision: MainDecision
    ) -> None:
        entry = (
            self.package.worldbook.get(decision.entry_id, viewer="player")
            if decision.entry_id else None
        )
        content = entry.text if entry is not None else "没有找到你能查看的相关资料。"
        event_id = f"{turn_id}:query"
        event = WorldEvent(
            event_id, "player_query", "player", None, before.tick, (),
            details={"text": text, "entry_id": decision.entry_id},
        )
        observation = Observation(
            f"{event_id}:result", event_id, "player", "worldbook", content, before.tick
        )
        self.store.commit(before.game_id, before.version, event, (observation,), ())

    def _act(
        self, before: Snapshot, turn_id: str, text: str, decision: MainDecision
    ) -> None:
        event_id = f"{turn_id}:action"
        rule = self.package.action_rules.get(decision.action_id or "")
        if rule is None:
            reason = "这个行动没有对应的剧本规则，世界状态未改变。"
            event = WorldEvent(
                event_id, "action_rejected", "player", None, before.tick + 1, (),
                details={"text": text, "action_id": decision.action_id, "reason": reason},
            )
            observations = (
                Observation(f"{event_id}:result", event_id, "player", "action_result", reason, event.tick),
            )
        else:
            event, direct = adjudicate_action(before, rule, event_id, text)
            observations = direct + physical_observations(before, event)
        self.store.commit(before.game_id, before.version, event, observations, ())
