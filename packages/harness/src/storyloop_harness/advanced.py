"""Advanced story contracts and operations for persistence and legacy integrations.

This explicit compatibility surface is separate from the ordinary TurnEngine facade."""
from storyloop_harness.core.actions import (
    ActionRule,
    adjudicate_action,
)
from storyloop_harness.core.contracts import (
    AgentContextCheckpoint,
    AgentContextEntry,
    Effect,
    Observation,
    PendingWork,
    PlayerInput,
    Snapshot,
    WorldEvent,
)
from storyloop_harness.core.decisions import (
    MainDecision,
)
from storyloop_harness.core.open_actions import (
    OpenActionOutcome,
    _read_path as read_path,
    validate_open_effects,
)
from storyloop_harness.core.perception import (
    physical_observations,
)
from storyloop_harness.core.state import (
    apply_event,
)
from storyloop_harness.core.token_budget import (
    estimate_tokens,
)
from storyloop_harness.core.turn_result import (
    TurnOutcome,
)
from storyloop_harness.runtime.player_input import (
    submit_player_input,
)
from storyloop_harness.runtime.player_knowledge import (
    PlayerEncounter,
    accepted_encounters,
    merge_knowledge,
)
from storyloop_harness.runtime.player_preferences import (
    current_player_preferences,
    player_preferences_scope,
)
from storyloop_harness.runtime.presentation import (
    SceneContext,
    StorySegment,
    segment_for_observation,
)
from storyloop_harness.runtime.runner import (
    RunResult,
    TurnRunner,
    WorkHandler,
    WorkResult,
    WorkSelector,
)
from storyloop_harness.runtime.schedule import (
    advance_time,
    scenario_cue,
)
from storyloop_harness.runtime.story_clock import (
    StoryClock,
)
from storyloop_harness.runtime.turn_progress import (
    TurnProgress,
    emit,
)
from storyloop_harness.world.prepared_opening import (
    render_prepared_opening,
    validate_prepared_opening,
)
from storyloop_harness.world.prologue import (
    save_prologue,
)
from storyloop_harness.world.status_fields import (
    StatusField,
    _value_at as value_at,
    project_status_fields,
    status_effects,
)
from storyloop_harness.world.worldbook import (
    Worldbook,
)

__all__ = ['ActionRule', 'AgentContextCheckpoint', 'AgentContextEntry', 'Effect', 'MainDecision', 'Observation', 'OpenActionOutcome', 'PendingWork', 'PlayerEncounter', 'PlayerInput', 'RunResult', 'SceneContext', 'Snapshot', 'StatusField', 'StoryClock', 'StorySegment', 'TurnOutcome', 'TurnProgress', 'TurnRunner', 'WorkHandler', 'WorkResult', 'WorkSelector', 'WorldEvent', 'Worldbook', 'accepted_encounters', 'advance_time', 'adjudicate_action', 'apply_event', 'current_player_preferences', 'emit', 'estimate_tokens', 'merge_knowledge', 'physical_observations', 'player_preferences_scope', 'project_status_fields', 'read_path', 'render_prepared_opening', 'save_prologue', 'scenario_cue', 'segment_for_observation', 'status_effects', 'submit_player_input', 'validate_open_effects', 'validate_prepared_opening', 'value_at']
