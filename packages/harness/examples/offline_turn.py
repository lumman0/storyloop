"""Run with: python examples/offline_turn.py (after installing storyloop-harness)."""
import asyncio
import sys
from pathlib import Path
from storyloop_harness import ScenarioPackage, TurnEngine, TurnInput
from storyloop_harness.testing import InMemoryGameStore, OfflineModel


async def main():
    package = ScenarioPackage.load(Path(__file__).parent / 'freeform')
    store = InMemoryGameStore()
    package.seed_game(store, 'offline')
    outcome = await TurnEngine(store, package, OfflineModel()).run_turn(
        TurnInput('offline', 'Hello', 'turn-1', package.version))
    print(outcome.narration)
    print(f'Snapshot version: {outcome.snapshot.version}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
