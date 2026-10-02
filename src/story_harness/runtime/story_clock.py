"""Elapsed-time policy for campaign turns, independent of scenario milestones."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TurnDuration = Literal["brief", "standard", "extended", "rest"]
PERIODS = ("上午", "中午", "下午", "晚上")


@dataclass(frozen=True)
class StoryClock:
    ticks_per_day: int

    def __post_init__(self) -> None:
        if type(self.ticks_per_day) is not int or self.ticks_per_day < 1:
            raise ValueError("ticks_per_day must be positive")

    def elapsed(self, duration: TurnDuration, before_tick: int) -> int:
        if duration == "rest":
            return self.ticks_per_day - before_tick % self.ticks_per_day
        return {"brief": 1, "standard": min(2, self.ticks_per_day),
                "extended": min(max(3, self.ticks_per_day // 2), self.ticks_per_day)}[duration]

    def period(self, tick: int) -> str:
        index = min(3, tick % self.ticks_per_day * 4 // self.ticks_per_day)
        return PERIODS[index]

    def passage(self, before_tick: int, after_tick: int, duration: TurnDuration) -> str:
        if after_tick <= before_tick:
            return ""
        day = after_tick // self.ticks_per_day + 1
        if after_tick // self.ticks_per_day > before_tick // self.ticks_per_day:
            if duration == "rest":
                return f"夜深了。你休息一晚，第 {day} 天的上午到了。"
            return f"这段经历持续到夜色过去，第 {day} 天的{self.period(after_tick)}到了。"
        preface = {"brief": "过了一会儿", "standard": "这件事持续了一阵",
                   "extended": "这件事花去了不少时间", "rest": "休息过后"}[duration]
        return f"{preface}，现在是第 {day} 天的{self.period(after_tick)}。"
