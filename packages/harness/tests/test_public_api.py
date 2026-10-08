import asyncio
import importlib.util
from pathlib import Path

import pytest


def test_public_offline_turn():
    assert importlib.util.find_spec('storyloop_harness') is not None, 'independent harness package missing'
    from storyloop_harness import ScenarioPackage, TurnEngine, TurnInput, TurnOutcome, GameStore, ModelPort
    from storyloop_harness.testing import InMemoryGameStore, OfflineModel
    package = ScenarioPackage.load(Path(__file__).parents[1] / 'examples/freeform')
    store = InMemoryGameStore()
    package.seed_game(store, 'offline')
    engine = TurnEngine(store, package, OfflineModel())
    request = TurnInput('offline', 'Hello', 'turn-1', package.version)
    result = asyncio.run(engine.run_turn(request))
    assert isinstance(result, TurnOutcome)
    assert result.narration.strip()
    assert result.snapshot.version > 0
    assert result.snapshot == store.load('offline')
    assert result.events
    assert result.model_usage
    replay = asyncio.run(engine.run_turn(request))
    assert replay.snapshot == result.snapshot
    assert replay.narration == result.narration
    assert replay.model_usage == ()


def test_wrong_scenario_version_does_not_commit():
    from storyloop_harness import ScenarioPackage, TurnEngine, TurnInput
    from storyloop_harness.testing import InMemoryGameStore, OfflineModel
    package = ScenarioPackage.load(Path(__file__).parents[1] / 'examples/freeform')
    store = InMemoryGameStore()
    package.seed_game(store, 'offline')
    before = store.load('offline')
    with pytest.raises(ValueError, match='version'):
        asyncio.run(TurnEngine(store, package, OfflineModel()).run_turn(
            TurnInput('offline', 'Hello', 'turn-1', 'wrong')))
    assert store.load('offline') == before


def test_example_prints_on_windows_legacy_console():
    import os
    import subprocess
    import sys
    example = Path(__file__).parents[1] / 'examples/offline_turn.py'
    result = subprocess.run([sys.executable, str(example)], capture_output=True,
                            env={**os.environ, 'PYTHONIOENCODING': 'cp950'})
    assert result.returncode == 0, result.stderr
    assert b'Snapshot version:' in result.stdout


def test_model_failure_and_cancellation_leave_state_untouched():
    from storyloop_harness import ScenarioPackage, TurnEngine, TurnInput
    from storyloop_harness.testing import InMemoryGameStore
    package = ScenarioPackage.load(Path(__file__).parents[1] / 'examples/freeform')
    for error in (RuntimeError('offline failure'), asyncio.CancelledError()):
        class FailingModel:
            async def __call__(self, *args, **kwargs):
                raise error
        store = InMemoryGameStore()
        package.seed_game(store, 'game')
        before = store.load('game')
        with pytest.raises(type(error)):
            asyncio.run(TurnEngine(store, package, FailingModel()).run_turn(
                TurnInput('game', 'Hello', 'turn-1', package.version)))
        assert store.load('game') == before
        assert not store.event_exists('game', 'turn-1:input')


def test_memory_commit_version_atomicity_and_isolation():
    from storyloop_harness.core.contracts import Snapshot, WorldEvent, Observation
    from storyloop_harness.testing import InMemoryGameStore
    store = InMemoryGameStore()
    store.create_game(Snapshot('game', 0, 0, {'value': 1}))
    event = WorldEvent('e', 'test', None, None, 0, ())
    unknown = Observation('o', 'missing', 'player', 'scene', 'text', 0)
    with pytest.raises(ValueError, match='unknown event'):
        store.commit('game', 0, event, (unknown,), ())
    assert not store.event_exists('game', 'e')
    assert store.load('game').version == 0
    result = store.commit('game', 0, event, (), ())
    result.data['value'] = 10
    assert store.load('game').data == {'value': 1}
    with pytest.raises(ValueError, match='version'):
        store.commit('game', 0, event, (), ())
    assert store.load('game').version == 1
