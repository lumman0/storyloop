"""Public turn input and shared result contract."""
from dataclasses import dataclass
from storyloop_harness.core.turn_result import TurnOutcome


@dataclass(frozen=True)
class TurnInput:
    game_id: str
    player_text: str
    turn_id: str
    scenario_version: str
