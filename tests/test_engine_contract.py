"""Shared time and bounded status guarantees across turn paths."""

import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_platform.legacy.main_agent import MainDecision
from storyloop_harness.agents.scene_turn import NarrativeTurn, SourceNarrativeTurn, SceneContextProjector
from storyloop_platform.runtime.game_session import GameSession
from storyloop_harness.runtime.player_input import submit_player_input
from storyloop_harness.runtime.schedule import advance_time
from storyloop_harness.runtime.story_clock import StoryClock
from storyloop_harness.runtime.single_call import SingleCallGameSession
from storyloop_platform.runtime.status_update import settle_status
from storyloop_harness.world.scenario import ScenarioPackage
from storyloop_harness.world.status_fields import parse_status_fields
from test_game_session import EXAMPLE, ScriptedMain, ReplyModel
from storyloop_platform.legacy.npc_agent import NpcAgentPool


@pytest.fixture
def world(tmp_path):
    store = SQLiteGameStore(str(tmp_path / "world.sqlite3"))
    package = replace(ScenarioPackage.load(EXAMPLE), initial_work=())
    package.seed_game(store, "game")
    return store, package


def test_beta_evening_conversation_stays_on_same_tick_and_rest_advances(world):
    store, package = world
    advance_time(store, "game", 7, "night")
    main = ScriptedMain(MainDecision(intent="speech", target_ids=["dockhand"], duration="brief"))
    pool = NpcAgentPool(store, lambda *_: ReplyModel())
    session = GameSession(store, package, lambda _: main, pool, 8,
                          story_clock=StoryClock(8, overnight_requires_rest=True))
    outcome = asyncio.run(session.run_turn("game", "晚安之前再聊一句", "night-chat"))
    assert outcome.snapshot.tick == 7
    assert "我听见了" in outcome.narration
    assert store.event_details("game", "night-chat:input")["duration_ticks"] == 0
    main.decision = MainDecision(intent="speech", target_ids=[], duration="rest")
    assert asyncio.run(session.run_turn("game", "休息", "rest")).snapshot.tick == 8


@pytest.mark.parametrize("duration", [-1, 1.5, True])
def test_invalid_duration_still_rejected_without_world_changes(world, duration):
    store, _ = world
    before = store.load("game")
    with pytest.raises(ValueError, match="duration_ticks"):
        submit_player_input(store, "game", "bad", "hello", duration_ticks=duration)
    assert store.load("game").version == before.version


def status_package(package):
    state = deepcopy(package.initial_state)
    state["player_stats"] = {"pressure": 3, "secret": 5}
    fields = parse_status_fields([
        {"id": "pressure", "label": "压力", "description": "压力越大越紧张",
         "path": ["player_stats", "pressure"], "bounds": {"min": 0, "max": 10, "max_delta": 2}},
        {"id": "secret", "label": "隐藏数值", "visible": False,
         "path": ["player_stats", "secret"], "bounds": {"min": 0, "max": 10, "max_delta": 2}},
    ], state)
    return replace(package, initial_state=state, status_fields=fields)


def test_plain_narrative_keeps_status_and_exposes_only_visible_declared_fields(world):
    store, base = world
    package = status_package(base)
    package.seed_game(store, "status")
    context = SceneContextProjector(store, package).project(store.load("status"), "我有些紧张")
    assert context.request["status_fields"] == [{
        "id": "pressure", "label": "压力", "value": 3, "min": 0, "max": 10,
        "max_delta": 2, "description": "压力越大越紧张",
    }]
    plan = NarrativeTurn.model_validate({"prose": "你感到压力增加。",
                                         "status_changes": [{"id": "pressure", "delta": 1}]}).for_storage()
    assert [item.model_dump() for item in plan.status_changes] == [{"id": "pressure", "delta": 1}]


@pytest.mark.parametrize("model", [NarrativeTurn, SourceNarrativeTurn])
@pytest.mark.parametrize("changes", [
    [{"id": "pressure", "delta": 1.5}], [{"id": "pressure", "delta": True}],
    [{"id": "pressure", "delta": "1"}], [{"id": "pressure"}],
    {"id": "pressure", "delta": 1}, None,
])
def test_malformed_status_cannot_silently_be_discarded(model, changes):
    with pytest.raises(ValueError):
        model.model_validate({"prose": "你感到压力增加。", "status_changes": changes})


@pytest.mark.parametrize("delta", [1, 99])
def test_plain_status_change_is_validated_before_prose_commit_and_applied_once(world, delta):
    store, base = world
    package = status_package(base)
    package.seed_game(store, "status")

    class Generator:
        async def generate(self, *_):
            return NarrativeTurn.model_validate({"prose": "你感到压力增加。",
                "status_changes": [{"id": "pressure", "delta": delta}]}).for_storage()

    session = SingleCallGameSession(store, package, Generator(), SceneContextProjector(store, package))

    async def run():
        before = store.load("status")
        if delta == 99:
            with pytest.raises(ValueError, match="delta"):
                await session.run_turn("status", "我有些紧张", "turn")
            assert store.load("status").version == before.version
            assert not store.event_exists("status", "turn:input")
            return
        outcome = await session.run_turn("status", "我有些紧张", "turn")
        async def propose(*_):
            return session.proposed_status("status", "turn")
        first = await settle_status(store, "status", "turn", "我有些紧张", package.status_fields,
                                     outcome.player_observations, propose)
        again = await settle_status(store, "status", "turn", "我有些紧张", package.status_fields,
                                     outcome.player_observations, propose)
        assert first.data["player_stats"]["pressure"] == 4
        assert again.version == first.version

    asyncio.run(run())


def test_shared_contracts_preserve_legacy_identity():
    from storyloop_harness.core.decisions import MainDecision as CoreDecision
    from storyloop_harness.core.turn_result import StorySegment, TurnOutcome
    from storyloop_harness.core.store_port import GameStore
    from storyloop_platform.legacy.main_agent import MainDecision as LegacyDecision
    from storyloop_platform.runtime.game_session import TurnOutcome as LegacyOutcome
    from storyloop_harness.runtime.presentation import StorySegment as LegacySegment
    from storyloop_platform.adapters.store import GameStore as LegacyStore

    assert CoreDecision is LegacyDecision
    assert TurnOutcome is LegacyOutcome
    assert StorySegment is LegacySegment
    assert GameStore is LegacyStore


@pytest.mark.parametrize("sample, expected", [("", 0), ("hello world", 11), ("你好世界", 6)])
def test_shared_token_estimator_preserves_legacy_values(sample, expected):
    from storyloop_harness.core.token_budget import estimate_tokens
    from storyloop_platform.runtime.agent_context import estimate_tokens as legacy_estimate

    assert estimate_tokens is legacy_estimate
    assert estimate_tokens(sample) == legacy_estimate(sample) == expected
