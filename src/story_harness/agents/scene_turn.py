"""Story-first generation with a small, optional persistence sidecar."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from agentscope.message import Msg
from agentscope.model import ChatModelBase
from pydantic import BaseModel, Field, field_validator

from story_harness.adapters.store import GameStore
from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry, session_id_for_game
from story_harness.agents.main_agent import MainDecision
from story_harness.agents.openai_formatter import ThinkingSafeOpenAIChatFormatter
from story_harness.core.contracts import AgentContextEntry, Snapshot
from story_harness.runtime.agent_context import estimate_tokens
from story_harness.runtime.player_preferences import current_player_preferences
from story_harness.runtime.story_clock import StoryClock
from story_harness.world.scenario import ScenarioPackage


class SceneReply(BaseModel):
    actor_id: str
    speech: str = Field(min_length=1)


class ProposedEffect(BaseModel):
    path: list[str]
    value: str | int | bool


class ProposedStatusChange(BaseModel):
    id: str
    delta: int


class ProposedAction(BaseModel):
    status: Literal["occurred", "attempted", "blocked"] = "attempted"
    player_result: str = ""
    sensory: str = ""
    effects: list[ProposedEffect] = Field(default_factory=list)


class ProposedNextAction(BaseModel):
    label: str
    input: str


class SharedMoment(BaseModel):
    actor_id: str
    fact: str = Field(min_length=1)


class SceneTurn(BaseModel):
    decision: MainDecision
    prose: str = Field(min_length=1)
    replies: list[SceneReply] = Field(default_factory=list)
    action: ProposedAction = Field(default_factory=ProposedAction)
    status_changes: list[ProposedStatusChange] = Field(default_factory=list)
    options: list[ProposedNextAction] = Field(default_factory=list)
    memories: list[SharedMoment] = Field(default_factory=list)
    story_first: bool = False


class NarrativeTurn(BaseModel):
    """Only prose is required; the sidecar helps save actor-scoped context."""

    prose: str = Field(min_length=1)
    replies: list[SceneReply] = Field(default_factory=list)
    options: list[ProposedNextAction] = Field(default_factory=list)
    memories: list[SharedMoment] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    interaction: Literal["speech", "inspect", "action"] = "speech"
    duration: Literal["brief", "standard", "extended", "rest"] = "brief"
    delivery: Literal["targets", "room", "private_message"] = "targets"
    witnessed: str = ""

    @field_validator("replies", "options", "memories", mode="before")
    @classmethod
    def valid_items(cls, value: object, info) -> list[BaseModel]:
        if not isinstance(value, list):
            return []
        model = {"replies": SceneReply, "options": ProposedNextAction,
                 "memories": SharedMoment}[info.field_name]
        valid = []
        for item in value:
            try:
                valid.append(model.model_validate(item))
            except (TypeError, ValueError):
                continue
        return valid

    @field_validator("participants", mode="before")
    @classmethod
    def valid_participants(cls, value: object) -> list[str]:
        return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []

    @field_validator("interaction", "duration", "delivery", mode="before")
    @classmethod
    def valid_label(cls, value: object, info) -> str:
        choices = {
            "interaction": ("speech", "inspect", "action"),
            "duration": ("brief", "standard", "extended", "rest"),
            "delivery": ("targets", "room", "private_message"),
        }
        return value if value in choices[info.field_name] else choices[info.field_name][0]

    @field_validator("witnessed", mode="before")
    @classmethod
    def valid_witnessed(cls, value: object) -> str:
        return value if isinstance(value, str) else ""

    def for_storage(self) -> SceneTurn:
        participants = list(dict.fromkeys([
            *self.participants,
            *(item.actor_id for item in self.replies),
            *(item.actor_id for item in self.memories),
        ]))
        return SceneTurn(
            decision=MainDecision(
                intent=self.interaction, duration=self.duration,
                target_ids=participants,
                channel="private_message" if self.delivery == "private_message" else "speech",
                audience="room" if self.delivery == "room" else "targets",
            ),
            prose=self.prose, replies=self.replies,
            options=self.options, memories=self.memories,
            action=ProposedAction(sensory=self.witnessed),
            story_first=True,
        )


@dataclass(frozen=True)
class SceneModelContext:
    request: dict[str, object]
    nearby_actor_ids: tuple[str, ...]
    focus_actor_ids: tuple[str, ...]


class SceneContextProjector:
    """Read independent, recipient-scoped histories without a compression call."""

    def __init__(self, store: GameStore, package: ScenarioPackage,
                 *, max_responders: int = 3, context_window_tokens: int = 65536,
                 clock: StoryClock | None = None, program=None) -> None:
        self.store = store
        self.package = package
        self.max_responders = max_responders
        self.context_window_tokens = context_window_tokens
        self.clock = clock
        self.program = program

    @staticmethod
    def _history(entries: list[AgentContextEntry], query: str,
                 *, recent: int, older: int, excerpt_chars: int = 400) -> list[dict[str, object]]:
        """Retain recent context plus relevant earlier, actor-owned milestones."""
        def excerpt(content: str) -> str:
            if len(content) <= excerpt_chars:
                return content
            head = excerpt_chars // 2
            return content[:head] + " … " + content[-head:]

        terms = set()
        for word in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{3,}", query.casefold()):
            if re.search(r"[\u4e00-\u9fff]", word):
                terms.update(word[index:index + 2] for index in range(len(word) - 1))
            else:
                terms.add(word)
        earlier = entries[:-recent] if len(entries) > recent else []
        notable = {"private_message", "campaign_choice", "shared_experience",
                   "witnessed", "outgoing_message", "background"}
        ranked = sorted(enumerate(earlier), key=lambda pair: (
            sum(term in pair[1].content.casefold() for term in terms) * 4
            + (2 if pair[1].channel in notable else 0), pair[0],
        ), reverse=True)
        chosen = {index for index, _ in ranked[:older]}
        selected = [entry for index, entry in enumerate(earlier) if index in chosen]
        selected.extend(entries[-recent:])
        return [{"channel": entry.channel, "text": excerpt(entry.content), "tick": entry.tick}
                for entry in selected]

    def project(self, snapshot: Snapshot, player_text: str) -> SceneModelContext:
        actors = snapshot.data.get("actors", {})
        player = actors.get("player", {}) if isinstance(actors, dict) else {}
        location = player.get("location") if isinstance(player, dict) else None
        nearby = tuple(actor_id for actor_id, _ in self.package.actor_cards
                       if isinstance(actors.get(actor_id), dict)
                       and actors[actor_id].get("location") == location)
        mentioned = [actor_id for actor_id, _ in self.package.actor_cards
                     if actor_id in player_text or self.package.actor_names[actor_id] in player_text]
        recent_targets = [actor_id for item in reversed(self.store.player_inputs_for(snapshot.game_id)[-4:])
                          for actor_id in item.target_ids if actor_id in nearby]
        focus = tuple(dict.fromkeys((*mentioned, *recent_targets, *nearby)))[:self.max_responders]

        player_checkpoint = self.store.agent_context_checkpoint(snapshot.game_id, "player")
        player_history = self._history(
            self.store.agent_context_entries(
                snapshot.game_id, "player", player_checkpoint.through_version),
            player_text, recent=10, older=4, excerpt_chars=700,
        )
        npc_contexts: list[dict[str, object]] = []
        for actor_id in focus:
            checkpoint = self.store.agent_context_checkpoint(snapshot.game_id, actor_id)
            entries = self.store.agent_context_entries(snapshot.game_id, actor_id,
                                                       checkpoint.through_version)
            npc_contexts.append({
                "id": actor_id, "name": self.package.actor_names[actor_id],
                "role_card": self.package.role_cards[actor_id][:1200],
                "own_summary": checkpoint.summary[:1200],
                "own_history": self._history(entries, player_text, recent=8, older=3),
            })
        campaign = snapshot.data.get("campaign")
        story_context = (self.program.current_action_context(snapshot)
                         if self.program is not None else {})
        recent_inputs = self.store.player_inputs_for(snapshot.game_id)[-4:]
        recent_visible = [item.content[:420] for item in
                          self.store.observations_for(snapshot.game_id, "player")[-6:]
                          if item.channel in {"scene", "narration", "dialogue"}]
        request: dict[str, object] = {
            "player_action": player_text, "presentation_mode": self.package.presentation_mode,
            "location": location, "tick": snapshot.tick,
            "day": campaign.get("day") if isinstance(campaign, dict) else None,
            "time_period": self.clock.period(snapshot.tick) if self.clock else None,
            "player_profile": snapshot.data.get("player_profile", {}),
            "nearby_people": {actor_id: self.package.actor_names[actor_id] for actor_id in nearby},
            "candidate_responders": list(focus),
            "public_setting": [item.text[:650] for item in
                               self.package.worldbook.visible_lore("player", limit=4)],
            "public_rules": [item.text[:700] for item in
                             self.package.worldbook.visible_rules("player", limit=4)],
            "player_summary": player_checkpoint.summary[:1200],
            "player_history": player_history,
            "npc_contexts": npc_contexts,
            "current_story_scene": story_context.get("scene", ""),
            "current_story_goal": story_context.get("goal", ""),
            "story_anchors": story_context.get("anchors", []),
            "recent_player_actions": [item.text[:200] for item in recent_inputs],
            "recent_visible_beats": recent_visible[-4:],
            "player_style_preferences": list(current_player_preferences()),
        }
        if isinstance(campaign, dict):
            request["player_recorded_choices"] = campaign.get("choices", {})
            request["player_sent_messages"] = {
                key: value[:200] for key, value in campaign.get("messages", {}).items()
                if isinstance(key, str) and isinstance(value, str) and value
            } if isinstance(campaign.get("messages"), dict) else {}
        budget = min(16000, max(4800, self.context_window_tokens * 2 // 3))
        while estimate_tokens(json.dumps(request, ensure_ascii=False)) > budget:
            if player_history:
                player_history.pop(0)
            elif any(item["own_history"] for item in npc_contexts):
                largest = max(npc_contexts, key=lambda item: len(item["own_history"]))
                largest["own_history"].pop(0)
            elif request["public_setting"]:
                request["public_setting"].pop()
            elif request["recent_visible_beats"]:
                request["recent_visible_beats"].pop(0)
            elif npc_contexts and any(item["role_card"] for item in npc_contexts):
                for item in npc_contexts:
                    item["role_card"] = item["role_card"][:max(0, len(item["role_card"]) // 2)]
            else:
                raise ValueError("player action exceeds the configured context window")
        return SceneModelContext(request, nearby, focus)


class SingleSceneGenerator:
    def __init__(self, model: ChatModelBase, package: ScenarioPackage,
                 telemetry: Telemetry | None = None) -> None:
        self.model = model
        self.package = package
        self.telemetry = telemetry or LangfuseTelemetry()
        self.formatter = ThinkingSafeOpenAIChatFormatter()

    async def generate(self, game_id: str, context: SceneModelContext) -> SceneTurn:
        system = (
            "你是互动故事的叙述者。优先回应 player_action 的完整意思，写出自然、具体的故事正文；"
            "玩家想完成一段日常活动，就呈现过程和即时结果，不拆成等待下次点击的工序。"
            "novel 模式使用第二人称，把角色对白融入 prose；interactive 模式在 prose 写环境与行动，"
            "角色发言写进 replies。不要替玩家增加决定或未说的话。"
            "结合 recent_visible_beats 避免重复前一幕，按 public_rules 保持剧本世界的一致性。"
            "npc_contexts 中每位角色的经历彼此独立；角色只依据自己的经历和当场可感知的事行动，"
            "不得把别人的私事、尚未公开的身份或玩家未说出口的想法当成已知事实。"
            "只让当前相关的少数角色回应。正文优先，其他字段仅供保存上下文："
            "participants 是本轮实际参与的角色 ID；interaction 中寒暄或说话用 speech，"
            "查看用 inspect，实际做事用 action；duration 中短对话用 brief，持续活动用 standard，"
            "长时间活动用 extended，睡觉用 rest；delivery 标记公开说话、定向说话或私信。"
            "replies 摘录角色实际说过的话；witnessed 只概括旁观者能感知的事实，不能写内心活动。"
            "memories 只记共同经历中值得以后提起的承诺、线索或细节，普通寒暄可以为空。"
            "正文写完后，再给出三个可选的后续行动；从已经发生的结果继续，不要求玩家重做本轮行动。"
            "只输出 NarrativeTurn，不补充状态裁决或流程阶段。"
        )
        prompt = await self.formatter.format(msgs=[
            Msg("system", system, "system"),
            Msg("player", json.dumps(context.request, ensure_ascii=False), "user"),
        ])
        with self.telemetry.span(
            "single-scene-generation",
            {"game_id": game_id, "candidate_actor_ids": list(context.focus_actor_ids)},
            kind="agent", input=context.request if self.telemetry.capture_content else None,
            session_id=session_id_for_game(game_id, self.package.package_id),
        ) as span:
            response = await self.model(prompt, structured_model=NarrativeTurn)
            result = NarrativeTurn.model_validate(response.metadata)
            result = result.model_copy(update={
                "prose": result.prose.replace("\\r\\n", "\n").replace("\\n", "\n").strip(),
                "replies": [item.model_copy(update={
                    "speech": item.speech.replace("\\r\\n", "\n").replace("\\n", "\n").strip(),
                }) for item in result.replies],
            })
            span.metric("story.single_scene_model_calls", 1.0)
            if self.telemetry.capture_content:
                span.update(output=result.model_dump())
            return result.for_storage()
