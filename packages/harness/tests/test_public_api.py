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


def test_public_engine_accepts_platform_settings_and_bounded_progress():
    from types import SimpleNamespace
    from storyloop_harness import ScenarioPackage, TurnEngine, TurnInput
    from storyloop_harness.testing import InMemoryGameStore, OfflineModel
    from storyloop_harness.runtime.story_clock import StoryClock
    from storyloop_harness.adapters.telemetry import NoopTelemetry
    package = ScenarioPackage.load(Path(__file__).parents[1] / 'examples/freeform')
    store = InMemoryGameStore()
    package.seed_game(store, 'settings')
    program = SimpleNamespace(current_action_context=lambda snapshot: {'goal': 'find the boat'})
    clock, telemetry = StoryClock(12), NoopTelemetry()
    async def legacy(snapshot, work):
        raise AssertionError('no legacy work seeded')
    engine = TurnEngine(store, package, OfflineModel(), clock=clock, program=program,
                        max_responders=1, context_window_tokens=8192, max_steps=3,
                        telemetry=telemetry, legacy_npc_reply=legacy)
    # Settings affect different collaborators; their identity is part of assembly correctness.
    assert engine.session.clock is clock
    assert engine.session.projector.clock is clock
    assert engine.session.projector.program is program
    assert engine.session.projector.max_responders == 1
    assert engine.session.projector.context_window_tokens == 8192
    assert engine.session.max_steps == 3
    assert engine.session.telemetry is telemetry
    assert engine.session.legacy_npc_reply is legacy
    progress = []
    async def observe(event):
        progress.append(event)
    result = asyncio.run(engine.run_turn(TurnInput('settings', 'Hello', 'one', package.version),
                                          max_tick=0, progress=observe))
    assert result.snapshot.tick == 0
    assert progress
    assert engine.proposed_options('settings', 'one')
    assert engine.proposed_status('settings', 'one') == []
    assert asyncio.run(engine.run_ready_work('settings'))


def test_documented_adapter_surfaces_export_story_types_without_product_types():
    from storyloop_harness import advanced, generation, telemetry, usage
    from storyloop_harness.core.contracts import Snapshot, WorldEvent
    assert advanced.Snapshot is Snapshot
    assert advanced.WorldEvent is WorldEvent
    assert callable(advanced.apply_event)
    assert callable(advanced.value_at)
    assert callable(advanced.read_path)
    for module in (advanced, generation, telemetry, usage):
        assert all(hasattr(module, name) and not name.startswith('_') for name in module.__all__)
        assert not any(any(word in name.lower() for word in ('wallet', 'billing', 'portal', 'sql'))
                       for name in module.__all__)
    assert generation.CompatibleOpenAIChatModel
    assert telemetry.NoopSpan
    assert usage.ModelUsage('offline', 'turn', 0, 0).input_tokens == 0
