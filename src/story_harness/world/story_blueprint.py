"""Source-grounded, model-led story material stored inside a scenario package."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SourceFact(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    text: str = Field(min_length=8, max_length=1600)
    source_ref: str = Field(min_length=2, max_length=160)
    visibility: Literal["public", "private", "system"] = "public"
    active_days: list[int] = Field(default_factory=list, max_length=100)
    keywords: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid_retrieval(self) -> SourceFact:
        if any(type(day) is not int or not 1 <= day <= 1000 for day in self.active_days):
            raise ValueError("source fact active_days must contain positive days")
        if any(not isinstance(word, str) or not 2 <= len(word.strip()) <= 40
               for word in self.keywords):
            raise ValueError("source fact keywords must be short nonempty text")
        return self


class StoryMilestone(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    day: int = Field(ge=1, le=1000)
    cue: str = Field(min_length=8, max_length=1200)
    source_ref: str = Field(min_length=2, max_length=160)
    required: bool = False
    terminal: bool = False


class SetupOption(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    label: str = Field(min_length=2, max_length=50)
    guidance: str = Field(min_length=2, max_length=350)
    source_ref: str = Field(min_length=2, max_length=160)


class SetupField(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    label: str = Field(min_length=1, max_length=40)
    required: bool = False
    max_length: int = Field(ge=1, le=500)


class StorySetup(BaseModel):
    player_options: list[SetupOption] = Field(min_length=1, max_length=8)
    tone_options: list[SetupOption] = Field(min_length=1, max_length=12)
    custom_fields: list[SetupField] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def unique_ids(self) -> StorySetup:
        for entries in (self.player_options, self.tone_options, self.custom_fields):
            ids = [entry.id for entry in entries]
            if len(ids) != len(set(ids)):
                raise ValueError("story setup IDs must be unique")
        return self

    def resolve(self, values: dict[str, str] | None) -> dict[str, str]:
        data = values or {}
        if not isinstance(data, dict) or any(not isinstance(value, str) for value in data.values()):
            raise ValueError("story setup must contain text values")
        allowed = {"player", "tone", *(field.id for field in self.custom_fields)}
        if set(data) - allowed:
            raise ValueError("story setup contains unknown fields")
        player = data.get("player", self.player_options[0].id)
        tone = data.get("tone", self.tone_options[0].id)
        if player not in {option.id for option in self.player_options}:
            raise ValueError("unknown player setup option")
        if tone not in {option.id for option in self.tone_options}:
            raise ValueError("unknown tone setup option")
        result = {"player": player, "tone": tone}
        for field in self.custom_fields:
            value = data.get(field.id, "").strip()
            if len(value) > field.max_length:
                raise ValueError(f"story setup {field.id} is too long")
            if field.required and player == "custom" and not value:
                raise ValueError(f"story setup {field.id} is required")
            if value:
                result[field.id] = value
        return result


class ActorSlot(BaseModel):
    actor_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    brief: str = Field(min_length=8, max_length=800)
    source_ref: str = Field(min_length=2, max_length=160)


class OpeningAction(BaseModel):
    label: str = Field(min_length=2, max_length=50)
    input: str = Field(min_length=2, max_length=500)


class StoryBlueprint(BaseModel):
    source_document: str = Field(min_length=3, max_length=200)
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    opening_focus: str = Field(min_length=10, max_length=2500)
    setup: StorySetup
    actor_slots: list[ActorSlot] = Field(default_factory=list, max_length=30)
    player_profiles: list[dict[str, str]] = Field(default_factory=list, max_length=20)
    player_profile_pools: dict[str, list[dict[str, str]]] = Field(default_factory=dict, max_length=8)
    player_intro_template: str | None = Field(default=None, min_length=1, max_length=2000)
    player_intro_variables: list[str] = Field(default_factory=list, max_length=20)
    opening_options: list[OpeningAction] = Field(default_factory=list, max_length=3)
    facts: list[SourceFact] = Field(min_length=1, max_length=100)
    milestones: list[StoryMilestone] = Field(default_factory=list, max_length=100)
    source_resolutions: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def unique_ids(self) -> StoryBlueprint:
        for entries in (self.actor_slots, self.facts, self.milestones):
            ids = [getattr(entry, "actor_id", None) or entry.id for entry in entries]
            if len(ids) != len(set(ids)):
                raise ValueError("story blueprint IDs must be unique")
        if sum(step.terminal for step in self.milestones) > 1:
            raise ValueError("story blueprint supports one terminal milestone")
        if (len(set(self.player_intro_variables)) != len(self.player_intro_variables)
                or any(not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", item)
                       for item in self.player_intro_variables)):
            raise ValueError("player intro variables must be unique simple identifiers")
        if any(not 1 <= len(pool) <= 20 for pool in self.player_profile_pools.values()):
            raise ValueError("prepared player profile pool requires 1–20 profiles")
        for profiles in (self.player_profiles, *self.player_profile_pools.values()):
            names = []
            for profile in profiles:
                if (not isinstance(profile.get("name"), str) or not profile["name"].strip()
                        or any(not isinstance(key, str) or not isinstance(value, str)
                               or not 0 < len(key) <= 64 or len(value) > 500
                               for key, value in profile.items())):
                    raise ValueError("prepared player profile requires bounded text and a name")
                names.append(profile["name"].strip())
            if len(set(names)) != len(names):
                raise ValueError("prepared player profile names must be unique within each pool")
        return self

    @classmethod
    def load(cls, path: str | Path, actor_ids: set[str]) -> StoryBlueprint:
        result = cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
        if {slot.actor_id for slot in result.actor_slots} != actor_ids:
            raise ValueError("story blueprint actor slots must match scenario actors")
        return result

    def public_setup(self) -> dict[str, object]:
        return self.setup.model_dump(exclude={"player_options": {"__all__": {"guidance", "source_ref"}},
                                              "tone_options": {"__all__": {"guidance", "source_ref"}}})

    def relevant_facts(self, day: int, player_text: str) -> list[str]:
        visible = [fact for fact in self.facts if fact.visibility in {"public", "system"}]
        general = [fact for fact in visible if not fact.active_days]
        current = [fact for fact in visible if day in fact.active_days]
        recalled = [fact for fact in visible if fact.active_days and day not in fact.active_days
                    and any(word.casefold() in player_text.casefold() for word in fact.keywords)]
        selected: list[SourceFact] = []
        for facts, limit in ((general, 6), (current, 8), (recalled, 4)):
            for fact in facts[:limit]:
                if fact not in selected and len(selected) < 16:
                    selected.append(fact)
        return [fact.text for fact in selected]

    def active_milestones(self, day: int, completed: dict[str, bool]) -> list[dict[str, object]]:
        today = [step for step in self.milestones
                 if step.day == day and not completed.get(step.id, False)]
        overdue = sorted((step for step in self.milestones
                          if step.required and step.day < day
                          and not completed.get(step.id, False)), key=lambda step: step.day)
        # Old unresolved hints must not hide the current day's story material.
        selected = today[:6]
        selected.extend(overdue[-(6 - len(selected)):] if len(selected) < 6 else [])
        return [{"id": step.id, "source_day": step.day, "cue": step.cue,
                 "overdue": step.day < day} for step in selected]
