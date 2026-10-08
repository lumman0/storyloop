"""Default single-call engine facade."""
from contextvars import ContextVar
from dataclasses import replace
from storyloop_harness.contracts import TurnInput, TurnOutcome
from storyloop_harness.ports import GameStore, ModelPort
from storyloop_harness.world.scenario import ScenarioPackage
from storyloop_harness.agents.scene_turn import SingleSceneGenerator, SceneContextProjector
from storyloop_harness.runtime.single_call import SingleCallGameSession
from storyloop_harness.models.usage import collect_usage


class _RecordingStore:
    """Collect only successful commits in the current asynchronous turn."""
    def __init__(self, store: GameStore):
        self.store = store
        self.records = ContextVar('turn_commits', default=None)

    def __getattr__(self, name):
        return getattr(self.store, name)

    def commit(self, game_id, expected_version, event, observations, new_work, consumed_work_id=None):
        result = self.store.commit(game_id, expected_version, event, observations, new_work, consumed_work_id)
        records = self.records.get()
        if records is not None and event is not None:
            records.append(event)
        return result


class TurnEngine:
    def __init__(self, store: GameStore, package: ScenarioPackage, model: ModelPort):
        self.package = package
        self.store = _RecordingStore(store)
        self.session = SingleCallGameSession(
            self.store, package, SingleSceneGenerator(model, package),
            SceneContextProjector(self.store, package))

    async def run_turn(self, turn: TurnInput) -> TurnOutcome:
        if turn.scenario_version != self.package.version:
            raise ValueError('scenario version does not match engine package')
        snapshot = self.store.load(turn.game_id)
        scenario = snapshot.data.get('scenario', {})
        if scenario.get('id') != self.package.package_id or scenario.get('version') != self.package.version:
            raise ValueError('saved scenario identity/version does not match engine package')
        events = []
        token = self.store.records.set(events)
        try:
            with collect_usage() as usage:
                result = await self.session.run_turn(turn.game_id, turn.player_text, turn.turn_id)
            return replace(result, events=tuple(events), model_usage=tuple(usage.records))
        finally:
            self.store.records.reset(token)
