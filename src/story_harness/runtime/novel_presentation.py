"""Durable second-person presentation for a completed freeform turn."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from story_harness.adapters.store import GameStore
from story_harness.core.contracts import WorldEvent
from story_harness.runtime.presentation import SceneContext, StorySegment, segment_for_observation
from story_harness.runtime.story_clock import StoryClock
from story_harness.runtime.turn_progress import TurnProgress, emit
from story_harness.world.scenario import ScenarioPackage


class NovelPresenter(Protocol):
    async def present(self, context: SceneContext) -> str: ...


async def present_freeform_novel(
    store: GameStore,
    package: ScenarioPackage,
    presenter: NovelPresenter,
    game_id: str,
    player_text: str,
    turn_id: str,
    segments: tuple[StorySegment, ...],
    progress: TurnProgress | None = None,
) -> tuple[str, tuple[StorySegment, ...]]:
    """Reuse committed prose on retries without turning it into a world observation."""
    event_id = f"{turn_id}:novel"
    saved_details = store.event_details(game_id, event_id)
    saved = saved_details.get("text") if saved_details is not None else None
    if saved is not None and not isinstance(saved, str):
        raise ValueError("saved novel presentation is invalid")
    if saved is None:
        snapshot = store.load(game_id)
        day = (snapshot.tick // package.ticks_per_day + 1
               if package.ticks_per_day else snapshot.tick + 1
               if package.time_unit == "day" else 1)
        period = (StoryClock(package.ticks_per_day).period(snapshot.tick)
                  if package.ticks_per_day else "")
        context = SceneContext(game_id, player_text, snapshot, segments, False, day, period)
        await emit(progress, "stage", stage="narrating")
        saved = (await presenter.present(context)).strip()
        if not saved:
            raise ValueError("novel presenter returned no prose")
        before = store.load(game_id)
        store.commit(
            game_id, before.version,
            WorldEvent(event_id, "novel_presented", None, turn_id, before.tick, (),
                       {"text": saved}), (), (),
        )
    segment = StorySegment("narration", saved)
    await emit(progress, "segment", segment=segment.to_dict())
    return saved, (segment,)


async def recover_last_freeform_novel(
    store: GameStore,
    package: ScenarioPackage,
    presenter: NovelPresenter,
    game_id: str,
    resume_ready_work: Callable[[str], Awaitable[object]],
) -> str | None:
    """Replay or finish the last CLI turn after a process restart."""
    inputs = store.player_inputs_for(game_id)
    if not inputs:
        return None
    previous = inputs[-1]
    if not previous.event_id.endswith((":input", ":query", ":action")):
        return None
    turn_id = previous.event_id.rsplit(":", 1)[0]
    if not store.event_exists(game_id, f"{turn_id}:novel"):
        await resume_ready_work(game_id)
    visible = tuple(
        segment_for_observation(store, game_id, item)
        for item in store.observations_for(game_id, "player")
        if item.event_id.startswith(f"{turn_id}:")
    )
    body, _ = await present_freeform_novel(
        store, package, presenter, game_id, previous.text, turn_id, visible,
    )
    return body
