"""Player-visible encounters, separate from private actor identity and memory."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field


class PlayerEncounter(BaseModel):
    actor_id: str
    evidence: str = Field(min_length=4, max_length=240)
    name_learned: bool = False


_INTRODUCTION = re.compile(
    r"我叫|我是|叫我|名叫|自我介绍|报上姓名|介绍|告诉你|说自己叫|"
    r"胸牌|胸前.*名牌|自己.*名牌|她的名牌|他的名牌|其名牌|"
    r"工作人员.*指着|主持人.*宣布"
)


def accepted_encounters(
    encounters: list[PlayerEncounter], prose: str, actor_names: dict[str, str],
) -> list[PlayerEncounter]:
    """Accept only encounters grounded in the player-visible scene.

    Text validation is deliberately conservative. It prevents a model from
    making a nameplate on a table into a known person in the sidebar.
    """
    accepted: list[PlayerEncounter] = []
    seen: set[str] = set()
    for item in encounters:
        name = actor_names.get(item.actor_id)
        evidence = item.evidence.strip()
        if not name or item.actor_id in seen or evidence not in prose:
            continue
        if "名牌" in evidence and not re.search(r"她|他|本人|胸前|衣服|佩戴|嘉宾|工作人员指着", evidence):
            continue
        identified = (item.name_learned and name in evidence
                      and _INTRODUCTION.search(evidence) is not None)
        accepted.append(item.model_copy(update={
            "evidence": evidence, "name_learned": bool(identified),
        }))
        seen.add(item.actor_id)
    return accepted


def merge_knowledge(state: dict[str, object], encounters: list[PlayerEncounter]) -> dict[str, list[str]]:
    seen = {item for item in state.get("seen_actor_ids", []) if isinstance(item, str)}
    named = {item for item in state.get("named_actor_ids", []) if isinstance(item, str)}
    for item in encounters:
        seen.add(item.actor_id)
        if item.name_learned:
            named.add(item.actor_id)
    return {"seen_actor_ids": sorted(seen), "named_actor_ids": sorted(named)}
