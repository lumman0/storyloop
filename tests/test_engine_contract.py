"""Platform status settlement consumes validated public engine proposals once."""
import asyncio
from dataclasses import replace
import pytest

from storyloop_harness import ScenarioPackage, TurnEngine, TurnInput
from storyloop_platform.adapters.store import SQLiteGameStore
from storyloop_platform.runtime.status_update import settle_status
from runtime_fakes import StructuredOfflineModel
from scenario_fixtures import EXAMPLE, status_package


@pytest.fixture
def world(tmp_path):
    store = SQLiteGameStore(str(tmp_path / 'world.sqlite3'))
    package = replace(ScenarioPackage.load(EXAMPLE), initial_work=())
    package.seed_game(store, 'game')
    return store, package


@pytest.mark.parametrize('delta', [1, 99])
def test_plain_status_change_is_validated_before_prose_commit_and_applied_once(world, delta):
    store, base = world
    package = status_package(base)
    package.seed_game(store, 'status')
    model = StructuredOfflineModel(lambda _: {'prose': '你感到压力增加。',
        'status_changes': [{'id': 'pressure', 'delta': delta}]})
    engine = TurnEngine(store, package, model)

    async def run():
        before = store.load('status')
        request = TurnInput('status', '我有些紧张', 'turn', package.version)
        if delta == 99:
            with pytest.raises(ValueError, match='delta'):
                await engine.run_turn(request)
            assert store.load('status').version == before.version
            assert not store.event_exists('status', 'turn:input')
            return
        outcome = await engine.run_turn(request)
        async def propose(*_):
            return engine.proposed_status('status', 'turn')
        first = await settle_status(store, 'status', 'turn', '我有些紧张', package.status_fields,
                                     outcome.player_observations, propose)
        again = await settle_status(store, 'status', 'turn', '我有些紧张', package.status_fields,
                                     outcome.player_observations, propose)
        assert first.data['player_stats']['pressure'] == 4
        assert again.version == first.version
    asyncio.run(run())
