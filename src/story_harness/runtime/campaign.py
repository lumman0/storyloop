"""Data-driven campaign clock and player choice gates around a ReAct session."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from story_harness.adapters.store import GameStore
from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry, session_id_for_game
from story_harness.core.contracts import Effect, Observation, Snapshot, WorldEvent


class ReactTurn(Protocol):
    async def run_turn(self, game_id: str, text: str, turn_id: str) -> Any: ...


@dataclass(frozen=True)
class CampaignOutcome:
    text: str
    snapshot: Snapshot
    gate_id: str | None
    complete: bool


@dataclass(frozen=True)
class CampaignProgram:
    program_id: str
    ticks_per_day: int
    final_tick: int
    steps: tuple[dict[str, Any], ...]

    @classmethod
    def load(cls, path: str | Path) -> CampaignProgram:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CampaignProgram:
        if not isinstance(raw, dict):
            raise ValueError("campaign must be an object")
        program_id, ticks_per_day, final_tick = raw.get("id"), raw.get("ticks_per_day"), raw.get("final_tick")
        steps = raw.get("steps")
        if not isinstance(program_id, str) or not program_id:
            raise ValueError("campaign requires an ID")
        if type(ticks_per_day) is not int or ticks_per_day < 1:
            raise ValueError("campaign requires positive ticks_per_day")
        if type(final_tick) is not int or final_tick < 1:
            raise ValueError("campaign requires positive final_tick")
        if not isinstance(steps, list) or not steps:
            raise ValueError("campaign requires steps")
        seen: set[str] = set()
        previous = -1
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get("id"), str) or not step["id"]:
                raise ValueError("campaign step requires an ID")
            if step["id"] in seen:
                raise ValueError("duplicate campaign step ID")
            seen.add(step["id"])
            at = step.get("at")
            if type(at) is not int or not previous <= at <= final_tick:
                raise ValueError("campaign steps must be ordered within final_tick")
            previous = at
            kind = step.get("kind")
            if kind not in {"scene", "choice", "message", "finale"}:
                raise ValueError("unknown campaign step kind")
            if kind in {"choice", "message"}:
                if not isinstance(step.get("prompt"), str) or not isinstance(step.get("options"), list):
                    raise ValueError("choice requires prompt and options")
                options = step["options"]
                if not options or any(not isinstance(option, dict) or not isinstance(option.get("id"), str)
                                      or not isinstance(option.get("label"), str) for option in options):
                    raise ValueError("invalid campaign choice option")
                if len({option["id"] for option in options}) != len(options):
                    raise ValueError("duplicate campaign option ID")
            if kind == "message":
                for item in step.get("incoming", []):
                    if (not isinstance(item, dict) or not isinstance(item.get("actor"), str)
                            or not isinstance(item.get("label"), str)
                            or not isinstance(item.get("text"), str)
                            or type(item.get("min_affinity")) is not int):
                        raise ValueError("invalid incoming message rule")
            if kind == "scene" and not isinstance(step.get("text"), str):
                raise ValueError("scene requires text")
            if kind == "finale" and (not isinstance(step.get("choice_key"), str)
                                      or type(step.get("threshold")) is not int):
                raise ValueError("finale requires choice_key and threshold")
            if kind == "finale" and (not isinstance(step.get("success_text"), str)
                                      or not isinstance(step.get("other_text"), str)):
                raise ValueError("finale requires success_text and other_text")
        finales = [step for step in steps if step["kind"] == "finale"]
        if len(finales) != 1 or steps[-1] is not finales[0] or finales[0]["at"] != final_tick:
            raise ValueError("campaign requires one terminal finale at final_tick")
        gates = {step["id"] for step in steps[:-1] if step["kind"] == "choice"}
        if finales[0]["choice_key"] not in gates:
            raise ValueError("finale must reference an earlier choice")
        return cls(program_id, ticks_per_day, final_tick, tuple(steps))

    def initial_state(self, actor_ids: list[str]) -> dict[str, Any]:
        return {
            "cursor": 0,
            "day": 1,
            "choices": {step["id"]: None for step in self.steps if step["kind"] in {"choice", "message"}},
            "answers": {step["id"]: "" for step in self.steps if step["kind"] == "choice"},
            "messages": {step["id"]: None for step in self.steps if step["kind"] == "message"},
            "incoming": {step["id"]: [] for step in self.steps if step["kind"] == "message"},
            "met": {actor_id: False for actor_id in actor_ids},
            "affinity": {actor_id: 0 for actor_id in actor_ids},
            "ending": None,
        }


class CampaignSession:
    """Advance a flexible milestone list without allowing a required choice to be skipped."""

    def __init__(self, store: GameStore, program: CampaignProgram, react: ReactTurn | None = None,
                 telemetry: Telemetry | None = None) -> None:
        self.store = store
        self.program = program
        self.react = react
        self.telemetry = telemetry or LangfuseTelemetry()
        self._locks: dict[str, asyncio.Lock] = {}

    async def start(self, game_id: str) -> CampaignOutcome:
        async with self._locks.setdefault(game_id, asyncio.Lock()):
            self._validate_snapshot(self.store.load(game_id))
            with self.telemetry.span("campaign-start", {"game_id": game_id, "campaign_id": self.program.program_id},
                                     session_id=session_id_for_game(game_id, self.program.program_id)) as span:
                resumed = await self._flush_ready(game_id)
                self._reconcile_encounters(game_id)
                result = self._drain(game_id, resumed)
                span.update(metadata={"tick": result.snapshot.tick, "gate_id": result.gate_id})
                return result

    async def submit(self, game_id: str, text: str, turn_id: str) -> CampaignOutcome:
        if not text.strip() or not turn_id:
            raise ValueError("campaign turn requires text and ID")
        async with self._locks.setdefault(game_id, asyncio.Lock()):
            with self.telemetry.span(
                "campaign-turn", {"game_id": game_id, "turn_id": turn_id, "campaign_id": self.program.program_id},
                input=text if self.telemetry.capture_content else None,
                session_id=session_id_for_game(game_id, self.program.program_id),
            ) as span:
                result = await self._submit_locked(game_id, text, turn_id)
                if not self.store.event_exists(game_id, f"{turn_id}:completed") and any(
                    self.store.event_exists(game_id, f"{turn_id}:{kind}")
                    for kind in ("choice", "advance", "input", "query", "action")
                ):
                    before = self.store.load(game_id)
                    after = self.store.commit(
                        game_id, before.version,
                        WorldEvent(f"{turn_id}:completed", "campaign_turn_completed", "player", None,
                                   before.tick, (), {"input": text, "display_text": result.text}),
                        (), (),
                    )
                    result = replace(result, snapshot=after)
                span.update(metadata={"tick": result.snapshot.tick, "day": result.snapshot.data["campaign"]["day"],
                                      "gate_id": result.gate_id, "complete": result.complete})
                span.metric("story.campaign_day", float(result.snapshot.data["campaign"]["day"]))
                if self.telemetry.capture_content:
                    span.update(output=result.text)
                return result

    async def recover_turn(self, game_id: str, turn_id: str) -> CampaignOutcome | None:
        """Finish a committed turn before a CLI assigns its ID to new input."""
        if self.store.event_exists(game_id, f"{turn_id}:completed"):
            return None
        committed = self._committed_operation(game_id, turn_id)
        if committed is None:
            return None
        _, details = committed
        original = details.get("request_text", details.get("text"))
        if not isinstance(original, str):
            raise ValueError("committed campaign turn has no recoverable input")
        return await self.submit(game_id, original, turn_id)

    def _committed_operation(self, game_id: str, turn_id: str) -> tuple[str, dict[str, object]] | None:
        for kind in ("choice", "advance", "input", "query", "action"):
            details = self.store.event_details(game_id, f"{turn_id}:{kind}")
            if details is not None:
                return kind, details
        return None

    async def _submit_locked(self, game_id: str, text: str, turn_id: str) -> CampaignOutcome:
        snapshot = self.store.load(game_id)
        self._validate_snapshot(snapshot)
        committed = self._committed_operation(game_id, turn_id)
        if committed is not None:
            _, details = committed
            original = details.get("request_text", details.get("text"))
            if original != text:
                raise ValueError("turn ID already belongs to a different input")
            resumed = await self._flush_ready(game_id)
            self._reconcile_encounters(game_id)
            replay = [item.content for item in self.store.observations_for(game_id, "player")
                      if item.event_id.startswith(f"{turn_id}:")]
            parts = resumed + [part for part in replay if part not in resumed]
            return self._drain(game_id, parts or ["上次操作已提交，继续当前进度。"])
        if snapshot.data["campaign"]["ending"] is not None:
            raise ValueError("campaign is complete")
        gate = self._due_gate(snapshot)
        if gate is not None:
            if not text.startswith("/choose "):
                return self._outcome(game_id, [self._prompt(gate)])
            parts = text.split(maxsplit=2)
            if len(parts) < 2:
                return self._outcome(game_id, [self._prompt(gate)])
            selected = next((option for option in gate["options"] if option["id"] == parts[1]), None)
            if selected is None:
                return self._outcome(game_id, ["这个选项不可用。", self._prompt(gate)])
            if gate["kind"] == "message" and selected["id"] != "skip":
                recipient = selected.get("recipient")
                if recipient not in snapshot.data["campaign"]["met"] or not snapshot.data["campaign"]["met"][recipient]:
                    return self._outcome(game_id, ["只能发送给已经互动过的嘉宾。", self._prompt(gate)])
                if len(parts) < 3 or not parts[2].strip():
                    return self._outcome(game_id, ["请在选项后写留言内容。", self._prompt(gate)])
            incoming = self._commit_choice(snapshot, gate, selected, parts[2] if len(parts) > 2 else "", turn_id, text)
            return self._drain(game_id, [selected.get("text", f"已选择：{selected['label']}")] + incoming)
        if text.startswith("/choose "):
            raise ValueError("no campaign choice is due")
        if text == "/next":
            self.store.commit(game_id, snapshot.version,
                              WorldEvent(f"{turn_id}:advance", "time_advanced", "player", None,
                                         snapshot.tick + 1, (), {"request_text": text}), (), ())
            parts = await self._flush_ready(game_id)
        else:
            if self.react is None:
                raise ValueError("free-form turns require a ReAct session")
            result = await self.react.run_turn(game_id, text, turn_id)
            parts = [result.narration]
            parts.extend(await self._flush_ready(game_id))
            if result.decision.intent == "speech":
                self._record_encounters(game_id, result.decision.target_ids, turn_id)
        return self._drain(game_id, parts)

    async def _flush_ready(self, game_id: str) -> list[str]:
        if not self.store.ready_work(game_id, self.store.load(game_id).tick):
            return []
        visible_before = {item.observation_id for item in self.store.observations_for(game_id, "player")}
        resume = getattr(self.react, "run_ready_work", None)
        if resume is None:
            raise ValueError("ready background work requires a work runner")
        for _ in range(16):
            await resume(game_id)
            if not self.store.ready_work(game_id, self.store.load(game_id).tick):
                return [item.content for item in self.store.observations_for(game_id, "player")
                        if item.observation_id not in visible_before]
        raise RuntimeError("background work budget exhausted; retry this turn ID")

    def _validate_snapshot(self, snapshot: Snapshot) -> None:
        scenario = snapshot.data.get("scenario")
        if not isinstance(scenario, dict) or scenario.get("id") != self.program.program_id:
            raise ValueError("game belongs to another scenario")
        campaign = snapshot.data.get("campaign")
        if not isinstance(campaign, dict) or type(campaign.get("cursor")) is not int:
            raise ValueError("game has no campaign state")
        for work in self.store.pending_work(snapshot.game_id):
            if work.kind == "npc_reply" and work.payload.get("duration_ticks", 1) != 0:
                raise ValueError("campaign NPC reply duration_ticks must be zero")

    def _record_encounters(self, game_id: str, target_ids: list[str], turn_id: str) -> None:
        if self.store.event_exists(game_id, f"{turn_id}:encounter"):
            return
        before = self.store.load(game_id)
        campaign = before.data["campaign"]
        effects: list[Effect] = []
        for actor_id in set(target_ids):
            if actor_id in campaign["met"]:
                effects.append(Effect(("campaign", "met", actor_id), True))
                effects.append(Effect(("campaign", "affinity", actor_id), campaign["affinity"][actor_id] + 1))
        if effects:
            self.store.commit(game_id, before.version,
                              WorldEvent(f"{turn_id}:encounter", "campaign_encounter", "player", turn_id,
                                         before.tick, tuple(effects)), (), ())

    def _reconcile_encounters(self, game_id: str) -> None:
        for item in self.store.player_inputs_for(game_id):
            if item.channel == "speech" and item.event_id.endswith(":input"):
                turn_id = item.event_id[:-len(":input")]
                if not self.store.event_exists(game_id, f"{turn_id}:encounter"):
                    self._record_encounters(game_id, list(item.target_ids), turn_id)

    def _due_gate(self, snapshot: Snapshot) -> dict[str, Any] | None:
        cursor = snapshot.data["campaign"]["cursor"]
        if cursor >= len(self.program.steps):
            return None
        step = self.program.steps[cursor]
        return step if step["at"] <= snapshot.tick and step["kind"] in {"choice", "message"} else None

    @staticmethod
    def _prompt(step: dict[str, Any]) -> str:
        options = " / ".join(f"{item['id']}={item['label']}" for item in step["options"])
        suffix = "；留言格式：/choose 嘉宾ID 留言内容" if step["kind"] == "message" else "；输入 /choose 选项ID"
        return f"{step['prompt']}\n可选：{options}{suffix}"

    def _commit_choice(self, before: Snapshot, step: dict[str, Any], option: dict[str, Any],
                       content: str, turn_id: str, request_text: str) -> list[str]:
        campaign = before.data["campaign"]
        effects = [Effect(("campaign", "cursor"), campaign["cursor"] + 1),
                   Effect(("campaign", "choices", step["id"]), option["id"])]
        if step["kind"] == "choice":
            effects.append(Effect(("campaign", "answers", step["id"]), content.strip()))
        observations: list[Observation] = []
        recipient = option.get("recipient") if step["kind"] == "message" and option["id"] != "skip" else None
        affinity_delta: dict[str, int] = {}
        if step["kind"] == "message":
            effects.append(Effect(("campaign", "messages", step["id"]), content if recipient else ""))
            if recipient:
                affinity_delta[recipient] = 1
        if option.get("meet") is not None:
            actor_id = option["meet"]
            if actor_id not in campaign["met"]:
                raise ValueError("choice refers to unknown actor")
            effects.append(Effect(("campaign", "met", actor_id), True))
        for actor_id, delta in option.get("affinity", {}).items():
            affinity_delta[actor_id] = affinity_delta.get(actor_id, 0) + delta
        for actor_id, delta in affinity_delta.items():
            if actor_id not in campaign["affinity"]:
                raise ValueError("choice affinity refers to unknown actor")
            effects.append(Effect(("campaign", "affinity", actor_id), campaign["affinity"][actor_id] + delta))
        event_id = f"{turn_id}:choice"
        player_summary = f"{step['prompt']} 你选择了{option['label']}。"
        if content.strip():
            player_summary += f" 你说：{content.strip()}"
        observations.append(Observation(f"{event_id}:player-choice", event_id, "player",
                                        "campaign_choice", player_summary, before.tick))
        notified = option.get("notify") or option.get("meet")
        if notified:
            observations.append(Observation(f"{event_id}:participant", event_id, notified,
                                            "shared_experience", f"玩家选择与你共同参与：{step['prompt']}", before.tick))
        incoming_texts: list[str] = []
        if step["kind"] == "message":
            senders: list[str] = []
            for index, rule in enumerate(step.get("incoming", [])):
                actor_id = rule["actor"]
                score = campaign["affinity"].get(actor_id, -1) + affinity_delta.get(actor_id, 0)
                if not campaign["met"].get(actor_id) or score < rule["min_affinity"]:
                    continue
                senders.append(actor_id)
                visible = f"来自{rule['label']}的心动留言：{rule['text']}"
                incoming_texts.append(visible)
                observations.append(Observation(f"{event_id}:incoming:{index}:player", event_id,
                                                "player", "private_message", visible, before.tick))
                observations.append(Observation(f"{event_id}:incoming:{index}:sender", event_id,
                                                actor_id, "outgoing_message", rule["text"], before.tick))
            effects.append(Effect(("campaign", "incoming", step["id"]), senders))
        if recipient:
            observations.append(Observation(f"{event_id}:recipient", event_id, recipient,
                                            "private_message", content, before.tick))
        event = WorldEvent(event_id, "campaign_choice", "player", None, before.tick,
                           tuple(effects), {"step_id": step["id"], "option_id": option["id"],
                                            "request_text": request_text})
        with self.telemetry.span("campaign-choice", {"step_id": step["id"], "option_id": option["id"],
                                                      "recipient_id": recipient}) as span:
            self.store.commit(before.game_id, before.version, event, tuple(observations), ())
            span.metric("story.campaign_choice", 1.0)
            span.metric("story.incoming_messages", float(len(incoming_texts)))
        return incoming_texts

    def _drain(self, game_id: str, parts: list[str]) -> CampaignOutcome:
        while True:
            before = self.store.load(game_id)
            campaign = before.data["campaign"]
            day = min(before.tick // self.program.ticks_per_day + 1,
                      self.program.final_tick // self.program.ticks_per_day + 1)
            if campaign["day"] != day:
                event = WorldEvent(f"campaign:day:{day}", "campaign_day", None, None,
                                   before.tick, (Effect(("campaign", "day"), day),))
                self.store.commit(game_id, before.version, event, (), ())
                continue
            cursor = campaign["cursor"]
            if cursor >= len(self.program.steps):
                break
            step = self.program.steps[cursor]
            if step["at"] > before.tick:
                break
            if step["kind"] in {"choice", "message"}:
                parts.append(self._prompt(step))
                break
            effects = [Effect(("campaign", "cursor"), cursor + 1)]
            event_id = f"campaign:{step['id']}"
            if step["kind"] == "scene":
                for actor_id, location in step.get("locations", {}).items():
                    effects.append(Effect(("actors", actor_id, "location"), location))
                for actor_id, delta in step.get("affinity", {}).items():
                    effects.append(Effect(("campaign", "affinity", actor_id), campaign["affinity"][actor_id] + delta))
                text = step["text"]
                for choice_id in step.get("reveal_answers", []):
                    answer = campaign["answers"].get(choice_id)
                    if answer:
                        text += f"\n{answer}"
            else:
                target = campaign["choices"].get(step["choice_key"])
                paired = target in campaign["affinity"] and campaign["affinity"][target] >= step["threshold"]
                ending = f"paired:{target}" if paired else "solo"
                effects.append(Effect(("campaign", "ending"), ending))
                if paired:
                    text = step["success_text"]
                elif target in campaign["affinity"]:
                    text = step.get("rejected_text", step["other_text"])
                else:
                    text = step["other_text"]
                if paired and campaign["choices"].get(step.get("bonus_choice_key")) == target:
                    text += "\n" + step.get("bonus_text", "")
            event = WorldEvent(event_id, f"campaign_{step['kind']}", None, None, before.tick,
                               tuple(effects), {"step_id": step["id"]})
            observations = [Observation(f"{event_id}:player", event_id, "player", "scene", text, before.tick)]
            if step["kind"] == "scene":
                for index, item in enumerate(step.get("observations", [])):
                    observations.append(Observation(f"{event_id}:private:{index}", event_id,
                                                    item["recipient"], "background", item["text"], before.tick))
            with self.telemetry.span("campaign-step", {"step_id": step["id"], "kind": step["kind"],
                                                      "tick": before.tick, "recipient_ids":
                                                      [item.recipient_id for item in observations]}) as span:
                self.store.commit(game_id, before.version, event, tuple(observations), ())
                span.metric("story.campaign_step", 1.0)
            parts.append(text)
        return self._outcome(game_id, parts)

    def _outcome(self, game_id: str, parts: list[str]) -> CampaignOutcome:
        snapshot = self.store.load(game_id)
        gate = self._due_gate(snapshot)
        return CampaignOutcome("\n\n".join(part for part in parts if part), snapshot,
                               gate["id"] if gate else None,
                               snapshot.data["campaign"]["ending"] is not None)
