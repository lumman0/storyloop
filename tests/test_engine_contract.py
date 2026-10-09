"""Shared time and bounded status guarantees across turn paths."""

import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest
from test_single_call import EXAMPLE, FakeGenerator, a_turn

from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_harness.agents.scene_turn import NarrativeTurn, SourceNarrativeTurn, SceneContextProjector
from storyloop_harness.runtime.schedule import advance_time
from storyloop_harness.runtime.story_clock import StoryClock
from storyloop_harness.runtime.single_call import SingleCallGameSession
from storyloop_platform.runtime.status_update import settle_status
from storyloop_harness.world.scenario import ScenarioPackage
from storyloop_harness.world.status_fields import parse_status_fields


@pytest.fixture
def world(tmp_path):
    store = SQLiteGameStore(str(tmp_path / "world.sqlite3"))
    package = replace(ScenarioPackage.load(EXAMPLE), initial_work=())
    package.seed_game(store, "game")
    return store, package


def test_evening_conversation_stays_on_same_tick_and_rest_advances(world):
    store, package = world
    advance_time(store, "game", 7, "night")
    clock = StoryClock(8, overnight_requires_rest=True)
    generator = FakeGenerator(a_turn(decision={"intent": "speech", "target_ids": ["dockhand"], "duration": "brief"}))
    session = SingleCallGameSession(store, package, generator,
        SceneContextProjector(store, package, clock=clock), clock=clock)
    outcome = asyncio.run(session.run_turn("game", "晚安之前再聊一句", "night-chat"))
    assert outcome.snapshot.tick == 7
    assert store.event_details("game", "night-chat:input")["duration_ticks"] == 0
    generator.turn = a_turn(decision={"intent": "speech", "target_ids": [], "duration": "rest"}, replies=[])
    assert asyncio.run(session.run_turn("game", "休息", "rest")).snapshot.tick == 8


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


@pytest.mark.parametrize("sample, expected", [("", 0), ("hello world", 11), ("你好世界", 6)])
def test_shared_token_estimator_values(sample, expected):
    from storyloop_harness.advanced import estimate_tokens
    assert estimate_tokens(sample) == expected
