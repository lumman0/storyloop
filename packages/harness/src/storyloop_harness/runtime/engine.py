"""Default single-call engine facade."""
from contextvars import ContextVar
from dataclasses import replace
from storyloop_harness.contracts import TurnInput, TurnOutcome
from storyloop_harness.ports import GameStore, ModelPort, CampaignContext
from storyloop_harness.runtime.story_clock import StoryClock
from storyloop_harness.runtime.turn_progress import TurnProgress
from storyloop_harness.runtime.runner import WorkHandler, RunResult
from storyloop_harness.adapters.telemetry import Telemetry
from storyloop_harness.agents.action_advisor import ActionOption
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
    def __init__(self, store: GameStore, package: ScenarioPackage, model: ModelPort,
                 *, clock: StoryClock | None = None, program: CampaignContext | None = None,
                 max_responders: int = 3, context_window_tokens: int = 65536,
                 max_steps: int = 8, telemetry: Telemetry | None = None,
                 legacy_npc_reply: WorkHandler | None = None):
        self.package = package
        self.store = _RecordingStore(store)
        self.session = SingleCallGameSession(
            self.store, package, SingleSceneGenerator(model, package, telemetry),
            SceneContextProjector(self.store, package, clock=clock, program=program,
                                  max_responders=max_responders,
                                  context_window_tokens=context_window_tokens),
            clock=clock, max_steps=max_steps, telemetry=telemetry,
            legacy_npc_reply=legacy_npc_reply)

    async def run_turn(self, turn: TurnInput, *, progress: TurnProgress | None = None,
                       max_tick: int | None = None) -> TurnOutcome:
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
                result = await self.session.run_turn(turn.game_id, turn.player_text, turn.turn_id,
                                                     progress=progress, max_tick=max_tick)
            return replace(result, events=tuple(events), model_usage=tuple(usage.records))
        finally:
            self.store.records.reset(token)

    async def run_ready_work(self, game_id: str,
                             progress: TurnProgress | None = None) -> RunResult:
        """Drain persisted work; callers collecting product usage also capture legacy replies."""
        return await self.session.run_ready_work(game_id, progress)

    def proposed_options(self, game_id: str, turn_id: str,
                         authored: tuple[ActionOption, ...] = ()) -> tuple[ActionOption, ...]:
        """Read validated action suggestions persisted by a completed turn."""
        return self.session.proposed_options(game_id, turn_id, authored)

    def proposed_status(self, game_id: str, turn_id: str) -> list[dict[str, object]]:
        """Read persisted status proposals for the product's status settlement."""
        return self.session.proposed_status(game_id, turn_id)
