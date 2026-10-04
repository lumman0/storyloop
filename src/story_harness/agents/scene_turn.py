"""One structured model generation for an ordinary story turn."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from agentscope.message import Msg
from agentscope.model import ChatModelBase
from pydantic import BaseModel, Field

from story_harness.adapters.store import GameStore
from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry, session_id_for_game
from story_harness.agents.main_agent import MainDecision
from story_harness.agents.openai_formatter import ThinkingSafeOpenAIChatFormatter
from story_harness.core.contracts import AgentContextEntry, Snapshot
from story_harness.core.open_actions import _read_path
from story_harness.runtime.agent_context import estimate_tokens
from story_harness.runtime.player_preferences import current_player_preferences
from story_harness.runtime.story_clock import StoryClock
from story_harness.world.scenario import ScenarioPackage
from story_harness.world.status_fields import _value_at


_RECURRING_SCENERY = {
    "窗与玻璃": ("窗外", "玻璃"),
    "雪景": ("雪光", "雪坡", "雪景", "落雪"),
    "室内光线": ("上午的光", "阳光", "灯光", "光线"),
    "室内暖意": ("暖气", "热气", "壁炉"),
}


def recent_scenery(passages: list[str]) -> list[str]:
    """Name scenery used in recent prose so the next turn can choose a new focus."""
    source = "\n".join(passages[-3:])
    return [name for name, phrases in _RECURRING_SCENERY.items()
            if any(phrase in source for phrase in phrases)]


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
                 *, recent: int, older: int) -> list[dict[str, object]]:
        """Retain recent context plus relevant earlier, actor-owned milestones."""
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
        return [{"channel": entry.channel, "text": entry.content[:260], "tick": entry.tick}
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
            player_text, recent=10, older=4,
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
        status = []
        for field in self.package.status_fields:
            if not field.automatically_updated:
                continue
            try:
                if (field.when_path is not None
                        and _value_at(snapshot.data, field.when_path) != field.when_equals):
                    continue
                current = _value_at(snapshot.data, field.path)
            except ValueError:
                continue
            status.append({"id": field.field_id, "label": field.label, "current": current,
                           "min": field.minimum, "max": field.maximum,
                           "max_delta": field.max_delta, "description": field.description})
        mutable = []
        for field in self.package.mutable_fields:
            try:
                current = _read_path(snapshot.data, field.path)
            except ValueError:
                continue
            mutable.append({"path": list(field.path), "current": current,
                            "allowed_next_values": list(field.next_values(current))})
        story_context = (self.program.current_action_context(snapshot)
                         if self.program is not None else {})
        recent_inputs = self.store.player_inputs_for(snapshot.game_id)[-4:]
        recent_options = []
        for player_input in recent_inputs[-2:]:
            details = self.store.event_details(snapshot.game_id, player_input.event_id) or {}
            stored_turn = details.get("single_call")
            if isinstance(stored_turn, dict) and isinstance(stored_turn.get("options"), list):
                recent_options.extend(stored_turn["options"][:3])
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
            "mutable_state": mutable,
            "updatable_status": status,
            "current_story_scene": story_context.get("scene", ""),
            "current_story_goal": story_context.get("goal", ""),
            "story_anchors": story_context.get("anchors", []),
            "authored_action_leads": story_context.get("leads", []),
            "recent_player_actions": [item.text[:200] for item in recent_inputs],
            "recent_visible_beats": recent_visible[-4:],
            "avoid_repeated_scenery": recent_scenery(recent_visible[-4:]),
            "recent_suggested_options": recent_options[-6:],
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
            elif request["recent_suggested_options"]:
                request["recent_suggested_options"].pop(0)
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
            "你是文游的单次场景主控。一次完成决策、相关角色回应、玩家可见正文、状态变化提议和三个可选后续行动。"
            "输入中的 npc_contexts 是彼此独立的角色视角：角色只能依据自己的 role_card、own_history、"
            "own_summary 和本场公开事实行动；绝不让一名角色说出另一名角色的私人经历或秘密。"
            "player_profile 是主角已经确定的身份；public_rules 是剧本约束，尤其是身份公布时机，"
            "不能因为 role_card 里有资料就提前让角色说出尚未公开的年龄、职业或秘密。"
            "只从 candidate_responders 选择最多三位立即回应；未被点名的群体场景也只让少数人说话。"
            "玩家的行动只以 player_action 为准，不代替玩家增加话语、决定或情绪。"
            "decision.intent 是 speech、inspect 或 action；一句话或简短问答 duration=brief，"
            "用餐等持续活动为 standard，整段长活动为 extended，明确睡觉为 rest。"
            "普通行动不需要预设 action_id。玩家主动加入、准备、制作或完成一件事时是 action，"
            "不能只把实际行动写成寒暄。按玩家输入的范围完成一段有起承转合的场景："
            "玩家说要做一件完整的事，就在本轮呈现其过程与即时结果；只说做其中一步，才停在那一步。"
            "玩家明确写出的连续行动都要在 prose 正文里实际发生，不能只在 action.player_result 或 options 中暗示已完成。"
            "不要为了状态字段把日常活动拆成必须由玩家逐一点击的工序。"
            "只有 mutable_state 明列的路径和 allowed_next_values 可以放进 action.effects；"
            "日常活动可只记录为本轮事件而没有 effects；不能把未成功的动作写成已经完成。"
            "status_changes 的 delta 不得超过对应 max_delta。"
            "prose 必须是本轮具体、连贯、有代入感的故事回应，使用第二人称‘你’，不要重复前文的固定景物。"
            "初见场景用可见外貌、得体寒暄、小动作和停顿形成自然的陌生人氛围，"
            "别让每个人一开口就生硬划界限；不要代替玩家作出心理决定。"
            "结合 recent_visible_beats 避开已用过的道具、句式和意象，不能把同一件事再发生一次。"
            "严格避开 avoid_repeated_scenery 列出的景物类型，本轮不要换近义词继续写它们。"
            "若行动花了时间，优先通过活动结果、人物进出与接下来的安排侧写进程；"
            "仅当时段明显变化或光线直接影响行动时才描写光线，"
            "不要只展示生硬的时间数字。"
            "novel 模式下 prose 自然整合角色的对白，replies 仍单独列出以便保存角色经历；"
            "interactive 模式下 prose 只写环境和行动，NPC 的发言只写进 replies，避免重复显示。"
            "不要泄露隐藏剧情、凭空新增人物或已发生事件。没有足够信息就简短写，不能凑字数。"
            "options 仅依据本轮可见剧情与 current_story_goal 提供三条不同、具体且能推进互动的行动；"
            "options 要从本轮已经发生的结果出发，不能再要求玩家重做已完成的事；"
            "不要照抄 authored_action_leads 或 recent_suggested_options。"
            "memories 默认为空；仅当玩家与某位在场角色共同经历了之后值得提起的细节、承诺、"
            "冲突或线索时，才给该角色写一条不超过180字的可观察事实，最多两位角色。"
            "日常备菜、普通寒暄不单独生成记忆。不能把猜测的心意或未说出口的想法写成事实。"
            "按钮 input 使用第一人称玩家意图，不写系统命令，也不重复 recent_player_actions。"
            "只输出符合 SceneTurn 的结构化结果，不调用工具。"
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
            response = await self.model(prompt, structured_model=SceneTurn)
            result = SceneTurn.model_validate(response.metadata)
            result = result.model_copy(update={
                "prose": result.prose.replace("\\r\\n", "\n").replace("\\n", "\n").strip(),
                "replies": [item.model_copy(update={
                    "speech": item.speech.replace("\\r\\n", "\n").replace("\\n", "\n").strip(),
                }) for item in result.replies],
            })
            span.metric("story.single_scene_model_calls", 1.0)
            if self.telemetry.capture_content:
                span.update(output=result.model_dump())
            return result
