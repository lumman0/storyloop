"""Exercise player input, NPC isolation and background time without a model API."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from agentscope.credential import OpenAICredential
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import TextBlock
from agentscope.model import ChatModelBase, ChatResponse

from storyloop_platform.legacy.npc_agent import NpcAgentPool
from storyloop_platform.legacy.npc_work import make_npc_reply_handler
from storyloop_harness.advanced import submit_player_input
from storyloop_harness.advanced import TurnRunner
from storyloop_harness import ScenarioPackage
from storyloop_harness.advanced import scenario_cue
from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_platform.adapters.telemetry import Telemetry


class OfflineReplyModel(ChatModelBase):
    """Deterministic test double; no simulated reasoning or world authority."""

    def __init__(self, actor_id: str) -> None:
        super().__init__(credential=OpenAICredential(api_key="offline"),
                         model=f"offline-{actor_id}", parameters=self.Parameters(),
                         stream=False)
        self.actor_id = actor_id
        self.formatter = OpenAIChatFormatter()

    async def __call__(self, messages: object, **kwargs: object) -> ChatResponse:
        return ChatResponse(content=[TextBlock(text=f"{self.actor_id}：我听到了。")],
                            is_last=True)


async def run_interaction_demo(
    path: str | Path, message: str = "你好，今天怎么样？", turns: int = 4,
    telemetry: Telemetry | None = None,
) -> dict[str, object]:
    if turns < 1:
        raise ValueError("turns must be positive")
    package = ScenarioPackage.load(path)
    actor_id = package.actor_cards[0][0]
    with TemporaryDirectory() as directory:
        store = SQLiteGameStore(str(Path(directory) / "game.sqlite3"))
        package.seed_game(store, "demo-game")
        pool = NpcAgentPool(store, lambda game_id, actor: OfflineReplyModel(actor), telemetry=telemetry)
        runner = TurnRunner(
            store,
            {
                "npc_reply": make_npc_reply_handler(pool, package.role_cards, package.actor_names),
                "scenario_cue": scenario_cue,
            },
            max_steps=8,
            telemetry=telemetry,
        )
        actors = store.load("demo-game").data["actors"]
        channel = (
            "speech"
            if actors["player"]["location"] == actors[actor_id]["location"]
            else "private_message"
        )
        processed: list[str] = []
        for index in range(turns):
            submit_player_input(
                store, "demo-game", f"input-{index + 1}", message,
                (actor_id,), channel=channel,
            )
            result = await runner.run_async("demo-game")
            processed.extend(result.processed_work_ids)
        return {
            "scenario": package.package_id,
            "time": {"tick": result.snapshot.tick, "day": (
                result.snapshot.tick // package.ticks_per_day + 1
                if package.ticks_per_day is not None else None
            )},
            "player_inputs": [item.text for item in store.player_inputs_for("demo-game")],
            "npc_observations": [item.content for item in store.observations_for("demo-game", actor_id)],
            "player_heard": [item.content for item in store.observations_for("demo-game", "player")],
            "processed": processed,
            "state": result.snapshot.data,
        }
