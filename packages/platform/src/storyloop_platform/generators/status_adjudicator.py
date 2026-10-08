"""Low-cost model proposal for script-declared status changes."""

from __future__ import annotations

import json

from storyloop_harness.generation import Msg
from agentscope.model import ChatModelBase
from pydantic import BaseModel, Field

from storyloop_platform.adapters.telemetry import LangfuseTelemetry, Telemetry
from storyloop_harness.generation import ThinkingSafeOpenAIChatFormatter
from storyloop_harness.advanced import Snapshot
from storyloop_harness.advanced import StatusField, value_at as _value_at


class StatusDelta(BaseModel):
    id: str
    delta: int


class StatusReview(BaseModel):
    changes: list[StatusDelta] = Field(default_factory=list)


class ModelStatusAdjudicator:
    def __init__(self, model: ChatModelBase, telemetry: Telemetry | None = None) -> None:
        self.model = model
        self.telemetry = telemetry or LangfuseTelemetry()
        self.formatter = ThinkingSafeOpenAIChatFormatter()

    async def propose(self, snapshot: Snapshot, player_text: str,
                      evidence: tuple[str, ...],
                      fields: tuple[StatusField, ...]) -> list[dict[str, object]]:
        request = {
            "player_action": player_text[:1000],
            "committed_player_visible_results": list(evidence),
            "tracked_fields": [
                {"id": field.field_id, "current": _value_at(snapshot.data, field.path),
                 "min": field.minimum, "max": field.maximum,
                 "max_delta": field.max_delta, "meaning": field.description}
                for field in fields
            ],
        }
        prompt = await self.formatter.format(msgs=[
            Msg("system", (
                "你只负责评估已发生的故事事件对已声明数值的影响。"
                "仅根据玩家行动及玩家实际看到的结果提出变化，不创造新事件、人物关系或秘密。"
                "没有足够证据、只是寒暄、数值含义不明确时返回空 changes。"
                "每个字段最多出现一次；delta 为整数且绝对值不能超过 max_delta。"
                "不要改变未列出的字段。只返回结构化 StatusReview。"
            ), "system"),
            Msg("status-evidence", json.dumps(request, ensure_ascii=False), "user"),
        ])
        with self.telemetry.span(
            "status-adjudication",
            {"game_id": snapshot.game_id, "tick": snapshot.tick,
             "status_field_ids": [field.field_id for field in fields],
             "evidence_count": len(evidence)},
            kind="agent", input=request if self.telemetry.capture_content else None,
        ) as span:
            response = await self.model(prompt, structured_model=StatusReview)
            review = StatusReview.model_validate(response.metadata)
            changes = [item.model_dump() for item in review.changes]
            span.update(metadata={"changes": changes})
            span.metric("story.status_proposed_changes", float(len(changes)))
            return changes
