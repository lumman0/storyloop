from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from story_harness.core.contracts import Observation, PendingWork, Snapshot, WorldEvent
from story_harness.core.perception import physical_observations
from story_harness.adapters.store import GameStore
from story_harness.adapters.telemetry import LangfuseTelemetry, Telemetry, session_id_for_game


@dataclass(frozen=True)
class WorkResult:
    event: WorldEvent | None
    observations: tuple[Observation, ...]
    new_work: tuple[PendingWork, ...]
    on_commit: Callable[[], None] | None = None
    on_abort: Callable[[], None] | None = None


@dataclass(frozen=True)
class RunResult:
    processed_work_ids: tuple[str, ...]
    remaining_work_ids: tuple[str, ...]
    snapshot: Snapshot


WorkHandler = Callable[[Snapshot, PendingWork], WorkResult | Awaitable[WorkResult]]
WorkSelector = Callable[
    [Snapshot, list[PendingWork]], PendingWork | Awaitable[PendingWork]
]
ObservationProjector = Callable[[Snapshot, WorldEvent], tuple[Observation, ...]]


class TurnRunner:
    """Process a bounded set of causally queued tasks."""

    def __init__(
        self,
        store: GameStore,
        handlers: Mapping[str, WorkHandler],
        max_steps: int,
        selector: WorkSelector | None = None,
        observation_projector: ObservationProjector = physical_observations,
        telemetry: Telemetry | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        self.store = store
        self.handlers = dict(handlers)
        self.max_steps = max_steps
        self.selector = selector
        self.observation_projector = observation_projector
        self.telemetry = telemetry or LangfuseTelemetry()

    def run(self, game_id: str) -> RunResult:
        """Run from synchronous code. Async callers should use run_async."""
        return asyncio.run(self.run_async(game_id))

    async def run_async(self, game_id: str) -> RunResult:
        snapshot = self.store.load(game_id)
        scenario = snapshot.data.get("scenario")
        scenario_id = scenario.get("id") if isinstance(scenario, dict) else None
        with self.telemetry.span(
            "game-turn",
            {"game_id": game_id, "state_version": snapshot.version, "tick": snapshot.tick},
            session_id=session_id_for_game(
                game_id, scenario_id if isinstance(scenario_id, str) else None
            ),
        ) as turn_span:
            result = await self._process_ready(game_id, snapshot)
            turn_span.update(output={
                "processed_work_ids": result.processed_work_ids,
                "state_version": result.snapshot.version,
                "tick": result.snapshot.tick,
            })
            turn_span.metric("story.work_processed", float(len(result.processed_work_ids)))
            turn_span.metric("story.work_remaining", float(len(result.remaining_work_ids)))
            return result

    async def _process_ready(self, game_id: str, snapshot: Snapshot) -> RunResult:
        processed: list[str] = []
        for _ in range(self.max_steps):
            ready = self.store.ready_work(game_id, snapshot.tick)
            if not ready:
                break
            required = [item for item in ready if item.mandatory]
            if required:
                work = required[0]
            elif self.selector is not None:
                choice = self.selector(snapshot, ready)
                if inspect.isawaitable(choice):
                    choice = await choice
                work = next(
                    (item for item in ready if item.work_id == choice.work_id),
                    None,
                )
                if work is None:
                    raise ValueError("selector chose work outside the ready queue")
            else:
                work = ready[0]
            if work.kind not in self.handlers:
                raise KeyError(f"no handler registered for {work.kind!r}")
            with self.telemetry.span(
                f"work:{work.kind}",
                {
                    "game_id": game_id,
                    "work_id": work.work_id,
                    "kind": work.kind,
                    "cause_id": work.cause_id,
                    "state_version": snapshot.version,
                },
            ) as work_span:
                result = self.handlers[work.kind](snapshot, work)
                if inspect.isawaitable(result):
                    result = await result
                try:
                    projected = (
                        self.observation_projector(snapshot, result.event)
                        if result.event is not None
                        else ()
                    )
                    snapshot = self.store.commit(
                        game_id,
                        snapshot.version,
                        result.event,
                        result.observations + projected,
                        result.new_work,
                        consumed_work_id=work.work_id,
                    )
                except BaseException:
                    if result.on_abort is not None:
                        result.on_abort()
                    raise
                if result.on_commit is not None:
                    result.on_commit()
                work_span.update(metadata={
                    "event_id": result.event.event_id if result.event else None,
                    "event_kind": result.event.kind if result.event else None,
                    "effect_paths": [".".join(effect.path) for effect in result.event.effects] if result.event else [],
                    "observation_ids": [item.observation_id for item in result.observations + projected],
                    "observation_recipient_ids": sorted({item.recipient_id for item in result.observations + projected}),
                    "new_work_ids": [item.work_id for item in result.new_work],
                    "committed_version": snapshot.version,
                })
            processed.append(work.work_id)

        return RunResult(
            tuple(processed),
            tuple(item.work_id for item in self.store.pending_work(game_id)),
            snapshot,
        )
