"""Character-authored private messages at campaign message gates."""

from __future__ import annotations

from collections.abc import Mapping

from storyloop_platform.legacy.npc_agent import NpcAgentPool, PreparedNpcReply


class NpcHeartMessageWriter:
    """Use each NPC's own persisted context when the script invites a message."""

    def __init__(self, pool: NpcAgentPool, role_cards: Mapping[str, str]) -> None:
        self.pool = pool
        self.role_cards = role_cards

    async def prepare(self, game_id: str, actor_id: str,
                      player_note: str | None) -> PreparedNpcReply:
        prompt = (
            "今晚节目组邀请你给玩家发一条私人心动留言。你可以根据你实际经历和性格，"
            "独立决定怎么措辞；只写你本人会发出的短信正文，20至70字，不写动作、署名或旁白。"
            "不要照抄别人的话，也不要声称知道你未亲历的私事。"
        )
        if player_note:
            prompt += f"玩家今晚发给你的原文是：{player_note}。你可以回应，但不必迎合或立刻表白。"
        else:
            prompt += "玩家今晚没有发给你的留言；不要假装收到。"
        return await self.pool.prepare_response(
            game_id, actor_id, self.role_cards[actor_id], prompt,
        )
