"""One-model-call ordinary turns with independently persisted NPC histories."""

from __future__ import annotations

import asyncio
import re
from weakref import WeakValueDictionary

from story_harness.core.store_port import GameStore
from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry, session_id_for_game
from story_harness.agents.action_advisor import ActionOption
from story_harness.core.decisions import MainDecision
from story_harness.agents.scene_turn import SceneContextProjector, SceneTurn, SingleSceneGenerator
from story_harness.core.actions import adjudicate_action
from story_harness.core.contracts import Effect, Observation, PendingWork, Snapshot, WorldEvent
from story_harness.core.open_actions import validate_open_effects
from story_harness.core.perception import physical_observations
from story_harness.core.turn_result import TurnOutcome
from story_harness.runtime.player_knowledge import accepted_encounters, merge_knowledge
from story_harness.core.turn_result import StorySegment
from story_harness.runtime.presentation import segment_for_observation
from story_harness.runtime.runner import RunResult, TurnRunner, WorkHandler, WorkResult
from story_harness.runtime.schedule import scenario_cue
from story_harness.runtime.story_clock import StoryClock
from story_harness.runtime.turn_progress import TurnProgress, emit
from story_harness.world.scenario import ScenarioPackage
from story_harness.world.status_fields import status_effects


def validated_options(raw: list[dict], recent: tuple[str, ...] = ()) -> tuple[ActionOption, ...]:
    """Keep only distinct generated actions; stale scene leads cannot refill a turn."""
    selected: list[ActionOption] = []
    used = {item.strip() for item in recent}
    for candidate in raw:
        try:
            item = ActionOption.model_validate(candidate)
        except Exception:
            continue
        if (item.input.strip() in used
                or re.search(r"/(?:choose|next|rest|continue)\b", item.input + item.label, re.I)
                or any(prior.input == item.input or prior.label == item.label for prior in selected)):
            continue
        selected.append(item)
        if len(selected) == 3:
            break
    return tuple(selected)


class SingleCallGameSession:
    """Generate once, commit authoritative facts, and replay NPC speech without a model."""

    def __init__(self, store: GameStore, package: ScenarioPackage,
                 generator: SingleSceneGenerator, projector: SceneContextProjector,
                 *, clock: StoryClock | None = None, max_steps: int = 8,
                 telemetry: Telemetry | None = None,
                 legacy_npc_reply: WorkHandler | None = None) -> None:
        self.store = store
        self.package = package
        self.generator = generator
        self.projector = projector
        self.clock = clock
        self.max_steps = max_steps
        self.telemetry = telemetry or LangfuseTelemetry()
        self.legacy_npc_reply = legacy_npc_reply
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def _npc_reply(self, snapshot: Snapshot, work: PendingWork) -> WorkResult:
        actor_id = work.payload["actor_id"]
        speech = work.payload["speech"]
        if not isinstance(actor_id, str) or actor_id not in self.package.actor_names:
            raise ValueError("single-call reply has unknown actor")
        if not isinstance(speech, str) or not speech.strip():
            raise ValueError("single-call reply is empty")
        profiles = snapshot.data.get("actor_profiles", {})
        profile = profiles.get(actor_id, {}) if isinstance(profiles, dict) else {}
        name = (profile.get("name") if isinstance(profile, dict)
                and isinstance(profile.get("name"), str) else self.package.actor_names[actor_id])
        knowledge = snapshot.data.get("player_knowledge")
        named = knowledge.get("named_actor_ids", []) if isinstance(knowledge, dict) else []
        player_label = (name if not isinstance(knowledge, dict) or actor_id in named
                        else "一位嘉宾")
        event = WorldEvent(f"{work.work_id}:spoken", "npc_spoke", actor_id,
                           work.cause_id, snapshot.tick, (),
                           {"player_message": work.payload.get("player_message", ""),
                            "speech": speech, "speaker_id": actor_id,
                            "speaker_name": player_label})
        observations: list[Observation] = []
        if self.package.presentation_mode == "interactive":
            observations.append(Observation(f"{event.event_id}:player-heard", event.event_id,
                                            "player", "dialogue", f"【{player_label}】\n{speech}", snapshot.tick))
        if not work.payload.get("private", False):
            actors = snapshot.data.get("actors", {})
            speaker_state = actors.get(actor_id, {}) if isinstance(actors, dict) else {}
            location = speaker_state.get("location") if isinstance(speaker_state, dict) else None
            for listener_id, state in actors.items():
                if (listener_id not in {"player", actor_id} and isinstance(state, dict)
                        and state.get("location") == location):
                    observations.append(Observation(
                        f"{event.event_id}:overheard:{listener_id}", event.event_id,
                        listener_id, "overheard", f"{name}对玩家说：{speech}", snapshot.tick,
                    ))
        return WorkResult(event, tuple(observations), ())

    def _runner(self) -> TurnRunner:
        handlers: dict[str, WorkHandler] = {"single_npc_reply": self._npc_reply,
                                             "scenario_cue": scenario_cue}
        if self.legacy_npc_reply is not None:
            handlers["npc_reply"] = self.legacy_npc_reply
        return TurnRunner(self.store, handlers,
                          self.max_steps, telemetry=self.telemetry)

    async def run_ready_work(self, game_id: str,
                             progress: TurnProgress | None = None) -> RunResult:
        async with self._locks.setdefault(game_id, asyncio.Lock()):
            return await self._runner().run_async(game_id)

    async def run_turn(self, game_id: str, player_text: str, turn_id: str,
                       progress: TurnProgress | None = None,
                       max_tick: int | None = None) -> TurnOutcome:
        return await self.run_turn_bounded(game_id, player_text, turn_id,
                                           max_tick=max_tick, progress=progress)

    async def run_turn_bounded(self, game_id: str, player_text: str, turn_id: str,
                               *, max_tick: int | None,
                               progress: TurnProgress | None = None) -> TurnOutcome:
        if not player_text.strip() or not turn_id:
            raise ValueError("turn requires text and ID")
        async with self._locks.setdefault(game_id, asyncio.Lock()):
            visible_before = {item.observation_id
                              for item in self.store.observations_for(game_id, "player")}
            event_id = f"{turn_id}:input"
            for kind in ("input", "query", "action"):
                if self.store.event_exists(game_id, f"{turn_id}:{kind}"):
                    event_id = f"{turn_id}:{kind}"
                    break
            saved = self.store.event_details(game_id, event_id)
            before = self.store.load(game_id)
            if saved is not None:
                if saved.get("text") != player_text or not isinstance(saved.get("single_call"), dict):
                    raise ValueError("turn ID already belongs to another action")
                plan = SceneTurn.model_validate(saved["single_call"])
            else:
                await emit(progress, "stage", stage="thinking")
                context = self.projector.project(before, player_text)
                with self.telemetry.span(
                    "single-call-turn", {"game_id": game_id, "turn_id": turn_id,
                                          "focus_actor_ids": list(context.focus_actor_ids)},
                    session_id=session_id_for_game(game_id, self.package.package_id),
                ) as span:
                    plan = await self.generator.generate(game_id, context)
                    plan = self._validate_plan(before, plan, context.focus_actor_ids,
                                               context.nearby_actor_ids)
                    span.metric("story.turn_model_calls", 1.0)
                await emit(progress, "stage", stage="committing")
                before = self._commit_player(before, turn_id, player_text, plan, max_tick)
            await emit(progress, "stage", stage="characters")
            processed = await self._runner().run_async(game_id)
            observations = tuple(item for item in self.store.observations_for(game_id, "player")
                                 if (item.observation_id not in visible_before
                                     or item.event_id.startswith(f"{turn_id}:")))
            segments = tuple(segment_for_observation(self.store, game_id, item)
                             for item in observations)
            if not segments:
                segments = (StorySegment("narration", plan.prose),)
            narration = "\n\n".join(item.body_text for item in segments)
            for segment in segments:
                await emit(progress, "segment", segment=segment.to_dict())
            return TurnOutcome(plan.decision, narration, observations,
                               processed.processed_work_ids, processed.snapshot,
                               False, segments)

    def _validate_plan(self, before: Snapshot, plan: SceneTurn,
                       focus: tuple[str, ...], nearby: tuple[str, ...]) -> SceneTurn:
        # Reject impossible numeric proposals before persisting their prose.
        status_effects(self.package.status_fields, before,
                       [change.model_dump() for change in plan.status_changes])
        decision = plan.decision
        allowed = set(focus)
        profiles = before.data.get("actor_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
        def actor_name(actor_id: str) -> str:
            profile = profiles.get(actor_id)
            return (profile.get("name") if isinstance(profile, dict)
                    and isinstance(profile.get("name"), str) else
                    self.package.actor_names.get(actor_id, ""))
        targets = list(dict.fromkeys(actor_id for actor_id in decision.target_ids
                                     if actor_id in allowed))[:len(allowed)]
        replies = []
        for item in plan.replies:
            if (item.actor_id in allowed and item.actor_id not in {reply.actor_id for reply in replies}
                    and item.speech.strip()):
                replies.append(item)
        if decision.intent in {"speech", "action"} and not targets:
            targets = [item.actor_id for item in replies]
        if decision.intent == "action" or (decision.intent == "speech" and decision.channel == "speech"):
            targets = [actor_id for actor_id in targets if actor_id in nearby]
        replies = [item for item in replies if item.actor_id in targets]
        if decision.channel == "private_message" and len(targets) > 1:
            targets = targets[:1]
            replies = [item for item in replies if item.actor_id in targets]
        decision = decision.model_copy(update={"target_ids": targets})
        milestones = []
        if self.package.story_blueprint is not None:
            progress = before.data.get("story_progress", {})
            completed = progress.get("completed", {}) if isinstance(progress, dict) else {}
            day = (before.tick // self.clock.ticks_per_day + 1 if self.clock else 1)
            active = {item["id"] for item in self.package.story_blueprint.active_milestones(
                day, completed if isinstance(completed, dict) else {},
            )}
            milestones = [item for item in dict.fromkeys(plan.milestones_fulfilled)
                          if item in active]
        prose = plan.prose.strip()
        if decision.intent == "action":
            outcome = plan.action
            effects = tuple(Effect(tuple(item.path), item.value) for item in outcome.effects)
            try:
                validate_open_effects(effects, self.package.mutable_fields, before.data)
                if outcome.status != "occurred" and effects:
                    raise ValueError("unsuccessful action cannot have state effects")
            except ValueError:
                plan = plan.model_copy(update={"action": outcome.model_copy(update={
                    "status": "attempted", "effects": [],
                    "player_result": "你尝试了这件事，但结果尚未得到确认。",
                    "sensory": "玩家尝试采取行动，结果尚不明确。",
                })})
                if not plan.story_first:
                    prose = plan.action.player_result
        if not prose:
            prose = "你停下来，留意眼前的变化。"
        encounters = (accepted_encounters(
            plan.encounters, prose,
            {actor_id: actor_name(actor_id) for actor_id in allowed},
        ) if self.package.story_blueprint is not None else [])
        memorable = (decision.intent == "speech" or
                     (decision.intent == "action" and
                      (plan.story_first or plan.action.status == "occurred")))
        participants = set(targets) & set(nearby) if memorable else set()
        memories = []
        for item in plan.memories:
            visibly_present = (
                actor_name(item.actor_id) in prose
                or (self.package.presentation_mode == "interactive"
                    and any(reply.actor_id == item.actor_id for reply in replies))
            ) if item.actor_id in participants else False
            if visibly_present and item.actor_id not in {
                prior.actor_id for prior in memories
            } and item.fact.strip():
                memories.append(item.model_copy(update={"fact": item.fact.strip()[:180]}))
            if len(memories) == (len(allowed) if self.package.story_blueprint else 2):
                break
        return plan.model_copy(update={"decision": decision, "replies": replies,
                                       "prose": prose, "memories": memories,
                                       "encounters": encounters,
                                       "milestones_fulfilled": milestones})

    def _commit_player(self, before: Snapshot, turn_id: str, player_text: str,
                       plan: SceneTurn, max_tick: int | None) -> Snapshot:
        decision = plan.decision
        duration_ticks = self.clock.elapsed(decision.duration, before.tick) if self.clock else 1
        if max_tick is not None:
            duration_ticks = min(duration_ticks, max(0, max_tick - before.tick))
        tick = before.tick + duration_ticks
        actors = before.data.get("actors", {})
        player = actors.get("player", {}) if isinstance(actors, dict) else {}
        location = player.get("location") if isinstance(player, dict) else None
        kind = {"speech": "input", "inspect": "query", "action": "action"}[decision.intent]
        event_id = f"{turn_id}:{kind}"
        details: dict[str, object] = {
            "text": player_text, "request_text": player_text,
            "before_tick": before.tick, "duration_ticks": duration_ticks,
            "duration": decision.duration, "target_ids": list(decision.target_ids),
            "channel": decision.channel, "audience": decision.audience,
            "single_call": plan.model_dump(),
        }
        effects: tuple[Effect, ...] = ()
        prose = plan.prose
        if decision.intent == "action":
            rule = self.package.action_rules.get(decision.action_id or "")
            if rule is not None:
                resolved, direct = adjudicate_action(before, rule, event_id,
                                                     player_text, duration_ticks,
                                                     decision.duration)
                effects = resolved.effects
                details.update(resolved.details)
                if not plan.story_first:
                    prose = "\n\n".join(item.content for item in direct) or prose
            else:
                effects = tuple(Effect(tuple(item.path), item.value)
                                for item in plan.action.effects)
                details.update({"action_id": None, "outcome": plan.action.status,
                                "location": location,
                                "sensory": plan.action.sensory or
                                ("" if plan.story_first else prose)})
        elif decision.intent == "inspect":
            entry = (self.package.worldbook.get(decision.entry_id, "player")
                     if decision.entry_id else None)
            if entry is not None:
                details["entry_id"] = entry.entry_id
                if not plan.story_first:
                    prose = entry.text
        if self.package.story_blueprint is not None and plan.milestones_fulfilled:
            effects += tuple(Effect(("story_progress", "completed", milestone_id), True)
                             for milestone_id in plan.milestones_fulfilled)
            if any(step.terminal and step.id in plan.milestones_fulfilled
                   for step in self.package.story_blueprint.milestones):
                effects += (Effect(("story_progress", "complete"), True),)
            details["milestones_fulfilled"] = plan.milestones_fulfilled
        knowledge = before.data.get("player_knowledge")
        if isinstance(knowledge, dict) and plan.encounters:
            updated_knowledge = merge_knowledge(knowledge, plan.encounters)
            if updated_knowledge != knowledge:
                effects += (Effect(("player_knowledge",), updated_knowledge),)
                details["player_encounters"] = [item.model_dump() for item in plan.encounters]
        event = WorldEvent(event_id, {"speech": "player_input",
                                      "inspect": "player_query",
                                      "action": "player_action"}[decision.intent],
                           "player", None, tick, effects, details)
        observations: list[Observation] = [
            Observation(f"{event_id}:scene", event_id, "player", "scene", prose, tick),
        ]
        campaign = before.data.get("campaign")
        day = (campaign.get("day") if isinstance(campaign, dict) else
               tick // self.clock.ticks_per_day + 1
               if self.package.story_blueprint is not None and self.clock else None)
        for memory in plan.memories:
            summary = memory.fact.strip()
            if type(day) is int and day > 0:
                summary = f"第{day}天：{summary}"
            observations.append(Observation(
                f"{event_id}:memory:{memory.actor_id}", event_id,
                memory.actor_id, "shared_experience", summary, tick,
            ))
        if decision.intent == "speech":
            hearers = (tuple(actor_id for actor_id, state in actors.items()
                             if actor_id != "player" and isinstance(state, dict)
                             and state.get("location") == location)
                       if decision.channel == "speech" and decision.audience == "room"
                       else tuple(decision.target_ids))
            observations.extend(Observation(f"{event_id}:heard:{actor_id}", event_id,
                                            actor_id, decision.channel, player_text, tick)
                                for actor_id in hearers)
        elif (decision.intent == "action" and isinstance(location, str)
              and details.get("sensory")):
            observations.extend(item for item in physical_observations(before, event)
                                if item.recipient_id != "player")
        pending = tuple(PendingWork(
            f"{event_id}:reply:{reply.actor_id}", "single_npc_reply", tick, 10, event_id,
            {"actor_id": reply.actor_id, "speech": reply.speech.strip(),
             "player_message": player_text if decision.intent == "speech" else "",
             "private": decision.channel == "private_message"},
        ) for reply in plan.replies)
        return self.store.commit(before.game_id, before.version, event,
                                 tuple(observations), pending)

    def proposed_status(self, game_id: str, turn_id: str) -> list[dict[str, object]]:
        details = next((self.store.event_details(game_id, f"{turn_id}:{kind}")
                        for kind in ("input", "query", "action")
                        if self.store.event_exists(game_id, f"{turn_id}:{kind}")), None)
        raw = details.get("single_call", {}) if isinstance(details, dict) else {}
        changes = raw.get("status_changes", []) if isinstance(raw, dict) else []
        return [item for item in changes if isinstance(item, dict)]

    def proposed_options(self, game_id: str, turn_id: str,
                         authored: tuple[ActionOption, ...] = ()) -> tuple[ActionOption, ...]:
        details = next((self.store.event_details(game_id, f"{turn_id}:{kind}")
                        for kind in ("input", "query", "action")
                        if self.store.event_exists(game_id, f"{turn_id}:{kind}")), None)
        raw = details.get("single_call") if isinstance(details, dict) else None
        if not isinstance(raw, dict):
            return authored
        progress = self.store.load(game_id).data.get("story_progress", {})
        if isinstance(progress, dict) and progress.get("complete") is True:
            return ()
        options = raw.get("options", [])
        previous = self.store.player_inputs_for(game_id)[-4:]
        recent = [item.text for item in previous]
        for item in previous[-2:-1]:
            prior = self.store.event_details(game_id, item.event_id) or {}
            scene = prior.get("single_call")
            if isinstance(scene, dict) and isinstance(scene.get("options"), list):
                for option in scene["options"]:
                    if isinstance(option, dict):
                        recent.extend(str(option.get(key, "")) for key in ("input", "label"))
        return validated_options(options if isinstance(options, list) else [], tuple(recent))
