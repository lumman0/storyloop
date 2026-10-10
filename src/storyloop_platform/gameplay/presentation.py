"""Pure gameplay response and delivery transformations."""

from __future__ import annotations

from dataclasses import replace

from storyloop_harness import ScenarioPackage
from storyloop_harness.advanced import StorySegment, StoryClock, StatusField, project_status_fields
from storyloop_harness.generation import ActionOption

from storyloop_platform.portal.presentation import campaign_interaction
from storyloop_platform.runtime.campaign import CampaignProgram


def package_for_mode(package: ScenarioPackage, play_mode: str) -> ScenarioPackage:
    # Delivery belongs to the save, while scenario data remains reusable.
    presentation = "novel" if play_mode == "campaign" else "interactive"
    return replace(package, presentation_mode=presentation)


def turn_view(game_id: str, catalog_id: str, mode: str, body: str,
          snapshot, guidance, *, complete: bool = False,
          opening: str = "", turn_id: str | None = None,
          segments: tuple[StorySegment, ...] = (),
          program: CampaignProgram | None = None, gate_id: str | None = None,
          time_of_day: str = "", presentation_mode: str = "interactive",
          action_options: tuple[ActionOption, ...] = (),
          clock: StoryClock | None = None,
          status_fields: tuple[StatusField, ...] = (),
          time_unit: str = "tick") -> dict:
    campaign = snapshot.data.get("campaign")
    progress_state = snapshot.data.get("story_progress", {})
    if isinstance(progress_state, dict) and progress_state.get("complete") is True:
        complete = True
    return {"game_id": game_id, "catalog_id": catalog_id, "mode": mode,
            "presentation_mode": presentation_mode,
            "opening": opening, "body": body,
            "segments": [part.to_dict() for part in segments],
            "interaction": campaign_interaction(program, snapshot, gate_id) if program else None,
            "suggestions": list(guidance.items),
            "action_options": [option.model_dump() for option in action_options],
            "tick": snapshot.tick, "state_version": snapshot.version,
            "day": (campaign.get("day") if isinstance(campaign, dict) else
                    snapshot.tick // clock.ticks_per_day + 1 if clock is not None else
                    snapshot.tick + 1 if time_unit == "day" else None),
            "time_of_day": time_of_day or (clock.period(snapshot.tick) if clock is not None else None),
            "status_fields": project_status_fields(status_fields, snapshot.data),
            "complete": complete, "turn_id": turn_id}
