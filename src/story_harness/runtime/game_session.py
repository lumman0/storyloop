"""Coordinate main ReAct decisions with the event-authoritative game runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from weakref import WeakValueDictionary

from story_harness.core.actions import adjudicate_action
from story_harness.agents.npc_agent import NpcAgentPool
from story_harness.core.contracts import Observation, PendingWork, Snapshot, WorldEvent
from story_harness.core.open_actions import OpenActionOutcome, validate_open_effects
from story_harness.agents.main_agent import MainDecision
from story_harness.runtime.npc_work import make_npc_reply_handler
from story_harness.core.perception import physical_observations
from story_harness.runtime.runner import RunResult, TurnRunner, WorkSelector
from story_harness.world.scenario import ScenarioPackage
from story_harness.runtime.schedule import scenario_cue
from story_harness.adapters.store import GameStore
from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry, TraceSpan, session_id_for_game
from story_harness.runtime.presentation import StorySegment, segment_for_observation
from story_harness.runtime.turn_progress import TurnProgress, emit
from story_harness.runtime.story_clock import StoryClock


class MainAgent(Protocol):
    async def decide(self, player_text: str) -> MainDecision: ...

    async def summarize(self, player_text: str, visible_results: list[str]) -> str: ...


class ActionResolver(Protocol):
    async def resolve(self, before: Snapshot, player_text: str,
                      suggested_targets: tuple[str, ...]) -> OpenActionOutcome: ...


@dataclass(frozen=True)
class TurnOutcome:
    decision: MainDecision
    narration: str
    player_observations: tuple[Observation, ...]
    processed_work_ids: tuple[str, ...]
    snapshot: Snapshot
    narration_fallback: bool = False
    segments: tuple[StorySegment, ...] = ()


async def compose_visible_narration(
    player_text: str,
    observations: tuple[Observation, ...],
    summarize: Callable[[str, list[str]], Awaitable[str]],
) -> str:
    segments = await compose_visible_segments(player_text, observations, summarize)
    return "\n\n".join(part.body_text for part in segments) or "暂时没有可见变化。"


async def compose_visible_segments(
    player_text: str,
    observations: tuple[Observation, ...],
    summarize: Callable[[str, list[str]], Awaitable[str]],
    dialogue_segment: Callable[[Observation], StorySegment] | None = None,
) -> tuple[StorySegment, ...]:
    parts: list[StorySegment] = []
    scene_results: list[str] = []
    for observation in observations:
        if observation.channel in {"dialogue", "private_message"}:
            if scene_results:
                parts.append(StorySegment("narration", await summarize(player_text, scene_results)))
                scene_results = []
            if observation.channel == "dialogue":
                parts.append(dialogue_segment(observation) if dialogue_segment
                             else StorySegment("dialogue", observation.content))
            else:
                parts.append(StorySegment("message", observation.content))
        elif observation.channel == "resolved_action":
            if scene_results:
                parts.append(StorySegment("narration", await summarize(player_text, scene_results)))
                scene_results = []
            parts.append(StorySegment("narration", observation.content))
        else:
            scene_results.append(observation.content)
    if scene_results:
        parts.append(StorySegment("narration", await summarize(player_text, scene_results)))
    return tuple(part for part in parts if part.text)


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
        max_npc_replies: int = 3,
        story_clock: StoryClock | None = None,
        action_resolver: ActionResolver | None = None,
    ) -> None:
        if type(max_npc_replies) is not int or max_npc_replies < 1:
            raise ValueError("max_npc_replies must be positive")
        self.store = store
        self.package = package
        self.main_factory = main_factory
        self.npc_pool = npc_pool
        self.max_steps = max_steps
        self.selector = selector
        self.telemetry = telemetry or LangfuseTelemetry()
        self.max_npc_replies = max_npc_replies
        self.story_clock = story_clock
        self.action_resolver = action_resolver
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def _runner(self) -> TurnRunner:
        return TurnRunner(
            self.store,
            {
                "npc_reply": make_npc_reply_handler(self.npc_pool, self.package.role_cards,
                                                     self.package.actor_names),
                "scenario_cue": scenario_cue,
            },
            max_steps=self.max_steps,
            selector=self.selector,
            telemetry=self.telemetry,
        )

    async def run_ready_work(self, game_id: str,
                             progress: TurnProgress | None = None) -> RunResult:
        """Resume due work after an external scheduler advances the game clock."""
        lock = self._locks.setdefault(game_id, asyncio.Lock())
        async with lock:
            before = self.store.load(game_id)
            scenario = before.data.get("scenario", {})
            if scenario.get("id") != self.package.package_id or scenario.get("version") != self.package.version:
                raise ValueError("game belongs to another scenario")
            async def committed(_snapshot: Snapshot, observations: tuple[Observation, ...]) -> None:
                await self._emit_visible_segments(game_id, observations, progress)

            return await self._runner().run_async(
                game_id, on_work_committed=committed if progress is not None else None,
            )

    async def run_turn(self, game_id: str, player_text: str, turn_id: str,
                       progress: TurnProgress | None = None) -> TurnOutcome:
        if not player_text.strip() or not turn_id:
            raise ValueError("turn requires text and an ID")
        lock = self._locks.setdefault(game_id, asyncio.Lock())
        async with lock:
            with self.telemetry.span(
                "story-turn", {"game_id": game_id, "turn_id": turn_id,
                               "scenario_id": self.package.package_id},
                input=player_text if self.telemetry.capture_content else None,
                session_id=session_id_for_game(game_id, self.package.package_id),
            ) as turn_span:
                try:
                    outcome = await self._run_locked_turn(game_id, player_text, turn_id,
                                                          turn_span, progress)
                except BaseException:
                    turn_span.metric("story.turn_success", 0.0)
                    raise
                turn_span.metric("story.turn_success", 1.0)
                return outcome

    async def _run_locked_turn(self, game_id: str, player_text: str,
                               turn_id: str, turn_span: TraceSpan,
                               progress: TurnProgress | None = None) -> TurnOutcome:
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
        # MainReActAgent rebuilds every turn's context from committed game data.
        main = self.main_factory(game_id)
        await emit(progress, "stage", stage="thinking")
        with self.telemetry.span(
            "main-decision", {"state_version": before.version, "tick": before.tick},
            kind="agent",
        ) as decision_span:
            decision = await main.decide(player_text)
            if (decision.intent == "speech" and decision.channel == "speech"
                    and len(decision.target_ids) > self.max_npc_replies):
                decision = decision.model_copy(update={"target_ids": decision.target_ids[:self.max_npc_replies]})
            decision_span.update(metadata={
                "intent": decision.intent, "target_ids": decision.target_ids,
                "duration": decision.duration,
                "audience": decision.audience,
                "entry_id": decision.entry_id, "action_id": decision.action_id,
            })
        await emit(progress, "stage", stage="committing")
        duration_ticks = (self.story_clock.elapsed(decision.duration, before.tick)
                          if self.story_clock is not None else 1)
        if decision.intent == "speech":
            self.store_input(game_id, turn_id, player_text, decision, duration_ticks)
        elif decision.intent == "inspect":
            self._inspect(before, turn_id, player_text, decision,
                          duration_ticks if self.story_clock is not None else 0)
        elif decision.intent == "action":
            if decision.action_id not in self.package.action_rules:
                await emit(progress, "stage", stage="adjudicating")
            await self._act(before, turn_id, player_text, decision, duration_ticks)
        else:
            raise ValueError(f"unsupported main intent: {decision.intent}")

        direct_observations = tuple(
            item for item in self.store.observations_for(game_id, "player")
            if item.observation_id not in visible_before
        )
        await self._emit_visible_segments(game_id, direct_observations, progress)

        runner = self._runner()
        await emit(progress, "stage", stage="characters")
        async def committed(_snapshot: Snapshot, observations: tuple[Observation, ...]) -> None:
            await self._emit_visible_segments(game_id, observations, progress)

        with self.telemetry.span("work-queue", {"max_steps": self.max_steps}) as queue_span:
            result = await runner.run_async(
                game_id, on_work_committed=committed if progress is not None else None,
            )
            queue_span.update(metadata={
                "processed_work_count": len(result.processed_work_ids),
                "remaining_work_count": len(result.remaining_work_ids),
            })
        new_observations = tuple(
            item for item in self.store.observations_for(game_id, "player")
            if item.observation_id not in visible_before
        )
        scene_results = [item.content for item in new_observations if item.channel != "dialogue"]
        dialogue_results = [item.content for item in new_observations if item.channel == "dialogue"]
        await emit(progress, "stage", stage="narrating")
        with self.telemetry.span(
            "main-narration", {"visible_observation_count": len(new_observations),
                               "dialogue_count": len(dialogue_results),
                               "scene_result_count": len(scene_results),
                               "observation_ids": [item.observation_id for item in new_observations],
                               "observation_channels": [item.channel for item in new_observations],
                               "strategy": ("defer_to_novel_presenter" if self.package.presentation_mode == "novel"
                                            else "preserve_dialogue_summarize_scene")},
            kind="agent",
            input=scene_results if self.telemetry.capture_content else None,
        ) as narration_span:
            try:
                if self.package.presentation_mode == "novel":
                    segments = tuple(segment_for_observation(self.store, game_id, item)
                                     for item in new_observations)
                else:
                    segments = await compose_visible_segments(
                        player_text, new_observations, main.summarize,
                        lambda item: segment_for_observation(self.store, game_id, item),
                    )
                narration = "\n\n".join(part.body_text for part in segments) or "暂时没有可见变化。"
                narration_fallback = False
            except Exception as error:
                narration = "\n\n".join(item.content for item in new_observations) or "暂时没有可见变化。"
                segments = tuple(segment_for_observation(self.store, game_id, item)
                                 for item in new_observations)
                narration_fallback = True
                narration_span.update(level="WARNING", status_message=type(error).__name__)
            narration_span.update(metadata={"narration_fallback": narration_fallback})
            if self.telemetry.capture_content:
                narration_span.update(output=narration)
        turn_span.update(metadata={
            "state_version": result.snapshot.version,
            "tick": result.snapshot.tick,
            "processed_work_count": len(result.processed_work_ids),
            "player_observation_count": len(new_observations),
            "narration_fallback": narration_fallback,
        })
        turn_span.metric("story.player_observations", float(len(new_observations)))
        turn_span.metric("story.narration_fallback", float(narration_fallback))
        if self.telemetry.capture_content:
            turn_span.update(output=narration)
        return TurnOutcome(
            decision, narration, new_observations,
            result.processed_work_ids, result.snapshot, narration_fallback, segments,
        )

    async def _emit_visible_segments(self, game_id: str, observations: tuple[Observation, ...],
                                     progress: TurnProgress | None) -> None:
        if self.package.presentation_mode == "novel":
            return
        for item in observations:
            if item.recipient_id == "player":
                await emit(progress, "segment",
                           segment=segment_for_observation(self.store, game_id, item).to_dict())

    def store_input(
        self, game_id: str, turn_id: str, text: str, decision: MainDecision,
        duration_ticks: int = 1,
    ) -> None:
        from story_harness.runtime.player_input import submit_player_input

        if any(actor_id not in self.package.role_cards for actor_id in decision.target_ids):
            raise ValueError("main agent selected an actor outside this scenario")
        submit_player_input(
            self.store, game_id, f"{turn_id}:input", text,
            tuple(decision.target_ids), channel=decision.channel, audience=decision.audience,
            duration_ticks=duration_ticks, duration=decision.duration,
        )

    def _inspect(
        self, before: Snapshot, turn_id: str, text: str, decision: MainDecision,
        duration_ticks: int = 0,
    ) -> None:
        entry = (
            self.package.worldbook.get(decision.entry_id, viewer="player")
            if decision.entry_id else None
        )
        content = entry.text if entry is not None else "没有找到你能查看的相关资料。"
        event_id = f"{turn_id}:query"
        event = WorldEvent(
            event_id, "player_query", "player", None, before.tick + duration_ticks, (),
            details={"text": text, "entry_id": decision.entry_id,
                     "before_tick": before.tick, "duration_ticks": duration_ticks,
                     "duration": decision.duration},
        )
        observation = Observation(
            f"{event_id}:result", event_id, "player", "worldbook", content, event.tick
        )
        self.store.commit(before.game_id, before.version, event, (observation,), ())

    async def _act(
        self, before: Snapshot, turn_id: str, text: str, decision: MainDecision,
        duration_ticks: int = 1,
    ) -> None:
        event_id = f"{turn_id}:action"
        rule = self.package.action_rules.get(decision.action_id or "")
        if rule is None:
            if self.action_resolver is None:
                raise ValueError("freeform action resolver is not configured")
            outcome = await self.action_resolver.resolve(before, text, tuple(decision.target_ids))
            validate_open_effects(outcome.effects, self.package.mutable_fields, before.data)
            actors = before.data.get("actors", {})
            player = actors.get("player", {}) if isinstance(actors, dict) else {}
            location = player.get("location") if isinstance(player, dict) else None
            if not isinstance(location, str):
                raise ValueError("player has no current location")
            targets = outcome.target_ids[:self.max_npc_replies]
            if any(actor_id not in self.package.actor_names
                   or not isinstance(actors.get(actor_id), dict)
                   or actors[actor_id].get("location") != location
                   for actor_id in targets):
                raise ValueError("open action target must be a nearby character")
            event = WorldEvent(
                event_id, "player_action", "player", None, before.tick + duration_ticks,
                outcome.effects,
                details={"text": text, "action_id": None, "outcome": outcome.status,
                         "target_ids": list(targets), "location": location,
                         "sensory": outcome.sensory,
                         "before_tick": before.tick, "duration_ticks": duration_ticks,
                         "duration": decision.duration},
            )
            observations = (Observation(
                f"{event_id}:result", event_id, "player", "resolved_action",
                outcome.player_result, event.tick),
            ) + tuple(item for item in physical_observations(before, event)
                      if item.recipient_id != "player")
            work = tuple(
                PendingWork(f"{event_id}:reply:{actor_id}", "npc_reply", event.tick,
                            10, event_id,
                            {"actor_id": actor_id, "player_message": outcome.sensory,
                             "duration_ticks": 0})
                for actor_id in targets
            )
        else:
            event, direct = adjudicate_action(before, rule, event_id, text,
                                              duration_ticks, decision.duration)
            observations = direct + physical_observations(before, event)
            work = ()
        self.store.commit(before.game_id, before.version, event, observations, work)
