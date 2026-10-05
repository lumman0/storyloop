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
from story_harness.runtime.player_knowledge import PlayerEncounter
from story_harness.runtime.player_preferences import current_player_preferences
from story_harness.runtime.story_clock import StoryClock
from story_harness.world.scenario import ScenarioPackage
from story_harness.world.status_fields import project_status_fields


class SceneReply(BaseModel):
    actor_id: str
    speech: str = Field(min_length=1)


class ProposedEffect(BaseModel):
    path: list[str]
    value: str | int | bool


class ProposedStatusChange(BaseModel):
    id: str
    delta: int = Field(strict=True)


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
    milestones_fulfilled: list[str] = Field(default_factory=list)
    encounters: list[PlayerEncounter] = Field(default_factory=list)


class NarrativeTurn(BaseModel):
    """Only prose is required; the sidecar helps save actor-scoped context."""

    prose: str = Field(min_length=1)
    replies: list[SceneReply] = Field(default_factory=list)
    options: list[ProposedNextAction] = Field(default_factory=list)
    memories: list[SharedMoment] = Field(default_factory=list)
    status_changes: list[ProposedStatusChange] = Field(default_factory=list)
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
            status_changes=self.status_changes,
            action=ProposedAction(sensory=self.witnessed),
            story_first=True,
        )


class SourceNarrativeTurn(NarrativeTurn):
    """Optional progress metadata only for source-driven scenario packages."""

    options: list[ProposedNextAction] = Field(min_length=3, max_length=3)
    milestones_fulfilled: list[str] = Field(default_factory=list)
    encounters: list[PlayerEncounter] = Field(default_factory=list)

    @field_validator("encounters", mode="before")
    @classmethod
    def valid_encounters(cls, value: object) -> list[PlayerEncounter]:
        if not isinstance(value, list):
            return []
        result = []
        for item in value:
            try:
                result.append(PlayerEncounter.model_validate(item))
            except (TypeError, ValueError):
                continue
        return result

    @field_validator("milestones_fulfilled", mode="before")
    @classmethod
    def valid_milestones(cls, value: object) -> list[str]:
        return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []

    def for_storage(self) -> SceneTurn:
        return super().for_storage().model_copy(update={
            "milestones_fulfilled": self.milestones_fulfilled,
            "status_changes": self.status_changes,
            "encounters": self.encounters,
        })


@dataclass(frozen=True)
class SceneModelContext:
    request: dict[str, object]
    nearby_actor_ids: tuple[str, ...]
    focus_actor_ids: tuple[str, ...]


class SceneContextProjector:
    """Project recipient-scoped history for a bounded set of responders.

    Public cast descriptions may cover additional people, but structured replies
    and memories are restricted to focus_actor_ids with projected role context.
    Remaining T07 work includes configurable source-fact/milestone budgets and
    prepublication validation of oversized required context. A single model sees
    multiple NPC contexts; this does not provide hard isolation between calls.
    """

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
        generated_profiles = snapshot.data.get("actor_profiles", {})
        if not isinstance(generated_profiles, dict):
            generated_profiles = {}
        def actor_name(actor_id: str) -> str:
            profile = generated_profiles.get(actor_id)
            return (profile.get("name") if isinstance(profile, dict)
                    and isinstance(profile.get("name"), str) else
                    self.package.actor_names[actor_id])
        def actor_card(actor_id: str) -> str:
            profile = generated_profiles.get(actor_id)
            return (profile.get("role_card") if isinstance(profile, dict)
                    and isinstance(profile.get("role_card"), str)
                    and profile["role_card"].strip() else
                    self.package.role_cards[actor_id])
        player = actors.get("player", {}) if isinstance(actors, dict) else {}
        location = player.get("location") if isinstance(player, dict) else None
        nearby = tuple(actor_id for actor_id, _ in self.package.actor_cards
                       if isinstance(actors.get(actor_id), dict)
                       and actors[actor_id].get("location") == location)
        mentioned = [actor_id for actor_id, _ in self.package.actor_cards
                     if (actor_id in player_text or actor_name(actor_id) in player_text)
                     and (self.package.story_blueprint is None or actor_id in nearby)]
        recent_inputs = self.store.player_inputs_for(snapshot.game_id, limit=4)
        recent_targets = [actor_id for item in reversed(recent_inputs)
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
            role_card = actor_card(actor_id).strip()[:1200]
            if not role_card:
                raise ValueError("responder role card is required")
            checkpoint = self.store.agent_context_checkpoint(snapshot.game_id, actor_id)
            entries = self.store.agent_context_entries(snapshot.game_id, actor_id,
                                                       checkpoint.through_version)
            npc_contexts.append({
                "id": actor_id, "name": actor_name(actor_id),
                "role_card": role_card,
                "own_summary": checkpoint.summary[:1200],
                "own_history": self._history(entries, player_text, recent=8, older=3),
            })
        campaign = snapshot.data.get("campaign")
        story_context = (self.program.current_action_context(snapshot)
                         if self.program is not None else {})
        recent_visible = [item.content[-900:] for item in
                          self.store.observations_for(snapshot.game_id, "player", limit=6)
                          if item.channel in {"scene", "narration", "dialogue"}]
        request: dict[str, object] = {
            "player_action": player_text, "presentation_mode": self.package.presentation_mode,
            "location": location, "tick": snapshot.tick,
            "day": campaign.get("day") if isinstance(campaign, dict) else None,
            "time_period": self.clock.period(snapshot.tick) if self.clock else None,
            "player_profile": snapshot.data.get("player_profile", {}),
            "nearby_people": {actor_id: actor_name(actor_id) for actor_id in nearby},
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
        updatable = {field.field_id: field for field in self.package.status_fields
                     if field.automatically_updated}
        request["status_fields"] = [
            {**row, "description": updatable[row["id"]].description,
             "max_delta": updatable[row["id"]].max_delta}
            for row in project_status_fields(self.package.status_fields, snapshot.data)
            if row["id"] in updatable
        ]
        blueprint = self.package.story_blueprint
        if blueprint is not None:
            knowledge = snapshot.data.get("player_knowledge", {})
            if not isinstance(knowledge, dict):
                knowledge = {}
            seen_ids = knowledge.get("seen_actor_ids", [])
            named_ids = knowledge.get("named_actor_ids", [])
            request["player_identity_knowledge"] = {
                "seen_actor_ids": seen_ids if isinstance(seen_ids, list) else [],
                "named_actor_ids": named_ids if isinstance(named_ids, list) else [],
            }
            day = snapshot.tick // self.clock.ticks_per_day + 1 if self.clock else 1
            request["day"] = day
            setup = snapshot.data.get("story_setup", {})
            tone_id = setup.get("tone") if isinstance(setup, dict) else None
            tone = next((item.guidance for item in blueprint.setup.tone_options
                         if item.id == tone_id), "")
            request["source_story_facts"] = blueprint.relevant_facts(day, player_text)
            request["source_resolutions"] = blueprint.source_resolutions
            progress = snapshot.data.get("story_progress", {})
            completed = progress.get("completed", {}) if isinstance(progress, dict) else {}
            request["source_story_milestones"] = blueprint.active_milestones(
                day, completed if isinstance(completed, dict) else {},
            )
            request["source_story_tone"] = tone
            request["public_cast"] = [
                {"id": actor_id, "name": actor_name(actor_id),
                 "seen_by_player": actor_id in seen_ids,
                 "name_known_to_player": actor_id in named_ids,
                 "appearance": (generated_profiles.get(actor_id, {}).get("public_profile", "")
                                if isinstance(generated_profiles.get(actor_id), dict) else "")}
                for actor_id in nearby
            ]
            request["nearby_people"] = {}
            request["current_story_scene"] = ""
            request["current_story_goal"] = ""
            request["story_anchors"] = []
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
            elif npc_contexts:
                if not any(len(item["role_card"]) > 160 for item in npc_contexts):
                    raise ValueError("configured context window cannot preserve responder role cards")
                for item in npc_contexts:
                    # Role identity is mandatory; never reduce a permitted
                    # responder's context to an empty card to fit the budget.
                    if len(item["role_card"]) > 160:
                        item["role_card"] = item["role_card"][:max(160, len(item["role_card"]) // 2)]
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
            "用人物动作、场景声响、外貌细节和没有说破的反应呈现性格与关系变化，"
            "让每段行动从上一幕的实际结果自然接上，不用固定的天气或光线句式开头。"
            "文字要有信息密度：短问候或看一眼通常用简短场景与直接反应即可，"
            "这类回合正文通常约一两百汉字；完整活动和重要群戏可写得更长，篇幅由事件决定。"
            "不要反复描写手指、目光、停顿、雪光等同一细节；完整活动或重要群戏才充分展开。"
            "每段描写至少要揭示新事实、呈现人物反应、改变关系或推进事件之一。"
            "慢热风格只约束关系建立的速度，不拖慢节目日程或把小动作拆成多轮。"
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
            "status_fields 给出可提议变化的数值 ID、当前值、含义、范围和单回合最大改变量；"
            "status_changes 只使用这些 ID 与整数 delta，依据本轮实际经历提出变化，不编造隐藏字段。"
            "选项应连接当前冲突、人物和近期剧情安排，至少两个通向不同的新互动或事件；"
            "如果上一幕刚完成一个选择，就让故事转到该选择带来的下一场面，别让玩家重复确认。"
            "不要连续几轮围绕同一件已处理的小物件打转，也不要凭空引入正文没有出现的道具。"
            "source_story_facts 与 source_story_tone 如有提供，代表剧本原始素材与本存档风格；"
            "source_story_milestones 是已到时机的剧情线索，不是必须机械播放的固定段落；"
            "一次回合不必填完当天所有线索，只在玩家行动和上一幕自然引出时推进；"
            "若正文中确实发生了某个线索事件，才把其 ID 放进 milestones_fulfilled。"
            "先承接 recent_visible_beats 的结尾，再回应玩家此刻的完整动作；"
            "不要把上一场尚未完成的目标当成本轮事实。"
            "public_cast 可用于群像描写；npc_contexts 只属于对应角色，绝不可让别人知道。"
            "若多位角色在正文说话，replies 要逐一摘录其说过的话并使用对应 actor_id，"
            "使每个人能记住自己的发言。"
            "day 和 time_period 是权威状态，不得在正文写出冲突的日期或时段。"
            "只输出约定的结构化结果，不补充流程阶段播报。"
        )
        if self.package.story_blueprint is not None:
            system += ("status_changes 仅在玩家明显表现出相应变化时可选填写，"
                       "不要为了填数值编造感情。原文描述互相冲突时遵循 source_resolutions。"
                       "public_cast 是作者参考名单，不表示所有人同处眼前，也不表示玩家认识他们。"
                       "依据 player_identity_knowledge 区分玩家见过谁、知道谁的姓名；"
                       "初见陌生人时先写可见形貌、行动与礼貌接触，经过自我介绍、他人明确介绍或本人随身标识后，"
                       "才在玩家视角将其姓名与人对应。桌上名牌只说明名字存在，不能据此给陌生人安上姓名。"
                       "本轮确实见到人物时，在 encounters 中给出 actor_id 和 prose 中的原文证据短句；"
                       "只有正文明确让玩家把姓名与本人对应，name_learned 才为 true。"
                       "每回合输出三个紧接本轮结尾的不同后续行动选项。输出 SourceNarrativeTurn。")
        else:
            system += "输出 NarrativeTurn。"
        schema = SourceNarrativeTurn if self.package.story_blueprint else NarrativeTurn
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
            response = await self.model(prompt, structured_model=schema)
            result = schema.model_validate(response.metadata)
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
